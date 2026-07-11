"""현재 보는 화면 스냅샷 → 시스템 프롬프트 주입 — 인용 프레이밍·가드레일 불변·report 공존."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import chat.chat as chatmod
from chat.chat import _build_system_prompt, chat
from chat.session import Session
from macro.engine import judge_regime

_JUDGE = judge_regime({"yield_spread": 0.6, "hy_spread": 2.0, "vix": 12.0})


def _resp(content):
    msg = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=msg)])


class _FakeClient:
    def __init__(self):
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return _resp("답변입니다.")


@pytest.fixture(autouse=True)
def _no_guardrail(monkeypatch):
    monkeypatch.setattr(chatmod, "classify", lambda t: "stock_analysis")


def test_omits_view_block_when_unset():
    prompt = _build_system_prompt(_JUDGE, Session())
    assert "현재 보고 있는 화면 스냅샷" not in prompt


def test_injects_view_block_when_set():
    s = Session()
    s.set_view_context("기준시각: 2026-07-11T09:00:00+00:00\n순자산 1,900만원 · 삼성전자 +24%")
    prompt = _build_system_prompt(_JUDGE, s)
    assert "현재 보고 있는 화면 스냅샷" in prompt
    assert "지어내지" in prompt  # 새 숫자 금지 프레이밍
    assert "삼성전자 +24%" in prompt  # 실제 스냅샷 본문
    assert "기준시각" in prompt  # 조회 시각(staleness 환기)


def test_chat_passes_view_context_into_system_message():
    s = Session()
    s.set_view_context("순자산 1,900만원 · SK하이닉스 -3%")
    client = _FakeClient()
    chat("내 잔고 어때?", _JUDGE, s, client=client)
    system_msg = client.calls[0]["messages"][0]["content"]
    assert "SK하이닉스 -3%" in system_msg


def test_view_and_report_blocks_coexist():
    s = Session()
    s.set_report_context("- 증권사: 한화투자증권\n- 요약: 실적 개선")
    s.set_view_context("순자산 1,900만원")
    prompt = _build_system_prompt(_JUDGE, s)
    assert "상담 컨텍스트로 불러온 애널리스트 리포트" in prompt  # report 블록
    assert "현재 보고 있는 화면 스냅샷" in prompt  # view 블록
    assert "한화투자증권" in prompt and "순자산 1,900만원" in prompt


def test_guardrail_still_blocks_with_view_context(monkeypatch):
    # 스냅샷이 있어도 위험 요청은 코드가 선차단(LLM 미호출) — 안전 불변.
    monkeypatch.setattr(chatmod, "classify", lambda t: "risk_guardrail")
    s = Session()
    s.set_view_context("순자산 1,900만원")
    client = _FakeClient()
    out = chat("이 종목 몰빵하면 반드시 오르지?", _JUDGE, s, client=client)
    assert out["popups"] == []
    assert client.calls == []  # LLM 미호출
