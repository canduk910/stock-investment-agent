"""StockReport Pydantic 스키마 테스트 — llm-safety-guide §4 (안전요건을 타입으로 강제).

핵심: 안전 요건을 '프롬프트 지시'가 아니라 '스키마 검증'으로 강제한다. 지시는 어길 수 있지만
검증 실패는 재시도된다. 그래서 여기서 검증하는 것은 곧 안전 계약이다:
- 종합의견 Literal["긍정적","중립","신중"] — "매수/매도" 라벨을 타입에서 원천 배제.
- 리스크요인 min_length=1 — 장밋빛 리포트 방지(리스크 최소 1개 강제).
- 투자포인트·리스크요인 max_length=3 — 과대 나열 방지.
- 면책고지 필수 — 누락 시 검증 실패.
LLM 출력 문체는 대상이 아니다. 필드 제약(타입·개수·필수)만 고정한다.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from chat.report_schema import StockReport


def _valid_kwargs(**overrides) -> dict:
    """검증 통과하는 기본 필드 세트 — 개별 테스트는 필요한 필드만 override."""
    base = {
        "종합의견": "중립",
        "요약": "현재 국면과 밸류에이션을 고려한 참고용 요약입니다.",
        "투자포인트": ["실적 개선 추세", "시장 점유율 확대"],
        "리스크요인": ["밸류에이션 부담", "업황 둔화 가능성"],
        "국면정합성": "현재 국면의 PER 상한 대비 다소 높은 편입니다.",
        "면책고지": "이 설명은 참고용이며 면허 있는 투자자문이 아닙니다.",
    }
    base.update(overrides)
    return base


# ── 정상 경로 ────────────────────────────────────────────────────────────────


def test_valid_report_passes():
    report = StockReport(**_valid_kwargs())
    assert report.종합의견 == "중립"
    assert len(report.리스크요인) == 2


@pytest.mark.parametrize("opinion", ["긍정적", "중립", "신중"])
def test_all_allowed_opinions_pass(opinion):
    report = StockReport(**_valid_kwargs(종합의견=opinion))
    assert report.종합의견 == opinion


# ── 안전 강제: 종합의견 enum ─────────────────────────────────────────────────


@pytest.mark.parametrize("bad", ["매수", "매도", "적극매수", "강력추천", "positive"])
def test_opinion_rejects_buy_sell_labels(bad):
    # 매수/매도류 명령형 라벨은 타입에서 원천 배제 — 안전 요건.
    with pytest.raises(ValidationError):
        StockReport(**_valid_kwargs(종합의견=bad))


# ── 안전 강제: 리스크요인 최소 1개 (장밋빛 방지) ─────────────────────────────


def test_risk_factors_empty_rejected():
    with pytest.raises(ValidationError):
        StockReport(**_valid_kwargs(리스크요인=[]))


def test_risk_factors_over_three_rejected():
    with pytest.raises(ValidationError):
        StockReport(**_valid_kwargs(리스크요인=["a", "b", "c", "d"]))


# ── 안전 강제: 투자포인트 최대 3개 ───────────────────────────────────────────


def test_investment_points_over_three_rejected():
    with pytest.raises(ValidationError):
        StockReport(**_valid_kwargs(투자포인트=["a", "b", "c", "d"]))


def test_investment_points_empty_allowed():
    # 투자포인트는 0개 허용(min 제약 없음) — 리스크만 최소 1개 강제.
    report = StockReport(**_valid_kwargs(투자포인트=[]))
    assert report.투자포인트 == []


# ── 필수 필드 누락 ───────────────────────────────────────────────────────────


def test_disclaimer_required():
    kwargs = _valid_kwargs()
    del kwargs["면책고지"]
    with pytest.raises(ValidationError):
        StockReport(**kwargs)


def test_summary_required():
    kwargs = _valid_kwargs()
    del kwargs["요약"]
    with pytest.raises(ValidationError):
        StockReport(**kwargs)


def test_regime_alignment_required():
    kwargs = _valid_kwargs()
    del kwargs["국면정합성"]
    with pytest.raises(ValidationError):
        StockReport(**kwargs)


# ── 안전 강제: 빈 문자열도 누락으로 취급(min_length=1, IMP-14) ────────────────


@pytest.mark.parametrize("field", ["요약", "국면정합성", "면책고지"])
def test_required_str_fields_reject_empty_string(field):
    # '키만 있으면 통과'가 아니라 비어있으면 검증 실패(면책고지='' 통과하던 구멍 차단).
    with pytest.raises(ValidationError):
        StockReport(**_valid_kwargs(**{field: ""}))


def test_risk_factor_empty_element_rejected():
    # 리스크요인=[''] 는 '리스크 1개'로 위장한 빈 항목 — 원소 min_length=1 로 거부(장밋빛 방지).
    with pytest.raises(ValidationError):
        StockReport(**_valid_kwargs(리스크요인=[""]))
    with pytest.raises(ValidationError):
        StockReport(**_valid_kwargs(리스크요인=["실질 리스크", ""]))


# ── 직렬화 계약(프론트·저장소가 소비) ────────────────────────────────────────


def test_model_dump_roundtrips_korean_keys():
    # 한글 필드명 그대로 dict 직렬화(report_store·프론트 렌더가 이 키로 소비).
    report = StockReport(**_valid_kwargs())
    dumped = report.model_dump()
    assert set(dumped) == {
        "종합의견",
        "요약",
        "투자포인트",
        "리스크요인",
        "국면정합성",
        "면책고지",
    }
