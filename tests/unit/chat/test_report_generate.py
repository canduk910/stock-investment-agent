"""리포트 생성·검증·폴백 테스트 — plan §"chat/report.py" (P2, OpenAI mock).

LLM 출력은 비결정적이라 대상 아님. 결정적 계약만 검증한다:
- 정상 JSON → StockReport 검증 통과 → validation_failed=False + report 반환.
- 불량(스키마 위반) → 1회 재요청 → 그래도 불량이면 폴백(정량요약만 + "AI 서술 생성 실패"
  + validation_failed=True). §5.1 부분실패 보존 — 리포트가 죽지 않고 정량요약은 남는다.
- 첫 시도가 불량이어도 재시도가 정상이면 통과(1회 재요청 성공 경로).
- CHAT_MODEL 단일출처로 호출(모델 문자열 산재 금지).
- 라이브 OpenAI 미호출(FakeClient mock).
경계(OpenAI 클라이언트)만 mock, 그 안쪽 파싱·검증·폴백 조립은 실제 코드로 통과.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from chat.report import generate_stock_report
from macro.engine import judge_regime

_JUDGE = judge_regime({"yield_spread": 0.6, "hy_spread": 2.0, "vix": 12.0})

# 최소 번들(정량요약·국면게이트). 실제 bundle shape 의 부분집합 — 생성 입력으로 충분.
_BUNDLE = {
    "ticker": "005930",
    "basic": {"name": "삼성전자"},
    "summary": {
        "current_per": 12.0,
        "avg_per": 15.0,
        "per_vs_avg": -20.0,
        "valuation_label": "저평가",
        "rev_cagr": 8.0,
    },
    "regime_gate": {
        "regime": "확장",
        "per_max": 15,
        "pbr_max": 1.5,
        "single_cap": 3,
        "entry_blocked": False,
        "per_over": False,
        "pbr_over": False,
    },
}

_VALID_REPORT = {
    "종합의견": "중립",
    "요약": "현재 국면과 밸류에이션을 고려한 참고용 요약입니다.",
    "투자포인트": ["실적 개선 추세"],
    "리스크요인": ["밸류에이션 부담"],
    "국면정합성": "현재 국면 PER 상한 이내입니다.",
    "면책고지": "이 설명은 참고용이며 면허 있는 투자자문이 아닙니다.",
}

# 스키마 위반(리스크요인 0개) — 검증 실패를 유발.
_INVALID_REPORT = {**_VALID_REPORT, "리스크요인": []}


def _resp(content: str):
    msg = SimpleNamespace(content=content)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class _FakeClient:
    """create() 가 준비된 응답(JSON 문자열)을 순서대로 반환(호출 kwargs 기록)."""

    def __init__(self, contents):
        self._contents = list(contents)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return _resp(self._contents.pop(0))


# ── 정상 경로 ────────────────────────────────────────────────────────────────


def test_valid_json_passes_validation():
    client = _FakeClient([json.dumps(_VALID_REPORT)])
    out = generate_stock_report(_BUNDLE, _JUDGE, client=client)

    assert out["validation_failed"] is False
    assert out["report"]["종합의견"] == "중립"
    assert out["report"]["리스크요인"] == ["밸류에이션 부담"]
    assert len(client.calls) == 1  # 첫 시도에서 통과 → 재요청 없음


def test_uses_chat_model_single_source():
    from chat.tools import CHAT_MODEL

    client = _FakeClient([json.dumps(_VALID_REPORT)])
    generate_stock_report(_BUNDLE, _JUDGE, client=client)
    assert client.calls[0]["model"] == CHAT_MODEL


def test_quant_summary_preserved_on_success():
    # 성공해도 정량요약은 함께 실려 온다(프론트가 정량+서술 동시 렌더).
    client = _FakeClient([json.dumps(_VALID_REPORT)])
    out = generate_stock_report(_BUNDLE, _JUDGE, client=client)
    assert out["quant_summary"] == _BUNDLE["summary"]


# ── 1회 재요청 성공 경로 ─────────────────────────────────────────────────────


def test_invalid_then_valid_recovers_on_retry():
    # 첫 응답 불량 → 1회 재요청 → 정상이면 통과.
    client = _FakeClient([json.dumps(_INVALID_REPORT), json.dumps(_VALID_REPORT)])
    out = generate_stock_report(_BUNDLE, _JUDGE, client=client)

    assert out["validation_failed"] is False
    assert out["report"]["종합의견"] == "중립"
    assert len(client.calls) == 2  # 재요청 1회


# ── 폴백 경로(재시도까지 실패) ───────────────────────────────────────────────


def test_persistent_invalid_falls_back():
    # 두 번 다 불량 → 폴백(정량요약만 + 실패 안내 + validation_failed=True).
    client = _FakeClient([json.dumps(_INVALID_REPORT), json.dumps(_INVALID_REPORT)])
    out = generate_stock_report(_BUNDLE, _JUDGE, client=client)

    assert out["validation_failed"] is True
    assert out["report"] is None
    assert "AI 서술 생성 실패" in out["message"]
    assert out["quant_summary"] == _BUNDLE["summary"]  # 부분실패 보존
    assert len(client.calls) == 2  # 최초 + 1회 재요청


def test_malformed_json_falls_back():
    # JSON 파싱 자체 실패도 폴백 경로(2회 다 깨진 JSON).
    client = _FakeClient(["{깨진 json", "여전히 깨짐"])
    out = generate_stock_report(_BUNDLE, _JUDGE, client=client)
    assert out["validation_failed"] is True
    assert out["report"] is None


def test_buy_sell_opinion_falls_back():
    # 종합의견 "매수"(enum 위반)도 검증 실패 → 재시도 → 폴백(명령형 라벨 원천 차단).
    bad = {**_VALID_REPORT, "종합의견": "매수"}
    client = _FakeClient([json.dumps(bad), json.dumps(bad)])
    out = generate_stock_report(_BUNDLE, _JUDGE, client=client)
    assert out["validation_failed"] is True


def test_openai_exception_falls_back():
    # OpenAI 호출 자체가 예외여도 크래시 없이 폴백.
    def boom(**kwargs):
        raise RuntimeError("network")

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=boom))
    )
    out = generate_stock_report(_BUNDLE, _JUDGE, client=client)
    assert out["validation_failed"] is True
    assert out["report"] is None
    assert out["quant_summary"] == _BUNDLE["summary"]
