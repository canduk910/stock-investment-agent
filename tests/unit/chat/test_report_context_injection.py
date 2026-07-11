"""리포트 상담 컨텍스트 → 시스템 프롬프트 주입(Phase D) — 출처귀속·판정금지·가드레일 불변."""
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


def test_build_system_prompt_omits_context_when_unset():
    prompt = _build_system_prompt(_JUDGE, Session())
    assert "상담 컨텍스트로 불러온 애널리스트 리포트" not in prompt


def test_build_system_prompt_injects_context_when_set():
    s = Session()
    s.set_report_context("- 증권사: 한화투자증권\n- 요약: 실적 개선")
    prompt = _build_system_prompt(_JUDGE, s)
    assert "상담 컨텍스트로 불러온 애널리스트 리포트" in prompt
    assert "리포트에 따르면" in prompt  # 출처 귀속 지시
    assert "한화투자증권" in prompt  # 실제 요약 본문


def test_chat_passes_context_into_system_message():
    s = Session()
    s.set_report_context("- 증권사: 미래에셋\n- 요약: 목표주가 상향")
    client = _FakeClient()
    chat("이 리포트 어떻게 봐?", _JUDGE, s, client=client)
    system_msg = client.calls[0]["messages"][0]["content"]
    assert "미래에셋" in system_msg and "목표주가 상향" in system_msg


def test_guardrail_still_blocks_even_with_context(monkeypatch):
    # 컨텍스트가 있어도 위험 요청은 코드가 선차단(LLM 미호출) — 안전 불변.
    monkeypatch.setattr(chatmod, "classify", lambda t: "risk_guardrail")
    s = Session()
    s.set_report_context("리포트 요약")
    client = _FakeClient()
    out = chat("이 종목 몰빵하면 반드시 오르지?", _JUDGE, s, client=client)
    assert out["popups"] == []
    assert client.calls == []  # LLM 미호출
