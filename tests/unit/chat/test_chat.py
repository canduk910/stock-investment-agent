"""agent 루프 + 인텐트 통합 테스트 — 계획 §5, 골격 §1 (OpenAI mock).

LLM 출력은 비결정적이라 대상 아님. 결정적 부분만: text/popups 분리(tool_calls 추출),
risk_guardrail 차단은 LLM 미호출·popups=[], 세션 append, OpenAI 실패 시 폴백(크래시 금지).
경계(OpenAI 클라이언트)만 mock 하고 그 안쪽 조립 로직은 실제 코드를 통과시킨다.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import chat.chat as chatmod
from chat.chat import chat
from chat.session import Session
from macro.engine import judge_regime

_JUDGE = judge_regime({"yield_spread": 0.6, "hy_spread": 2.0, "vix": 12.0})


def _tool_call(name, args, cid="call_1"):
    return SimpleNamespace(
        id=cid, function=SimpleNamespace(name=name, arguments=json.dumps(args))
    )


def _resp(content=None, tool_calls=None, finish_reason="stop"):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish_reason, message=msg)])


class _FakeClient:
    """create() 가 호출될 때마다 준비된 응답을 순서대로 반환(호출 횟수 기록)."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


@pytest.fixture(autouse=True)
def _no_guardrail(monkeypatch):
    # 기본은 비위험 라벨(LLM 경로). 개별 테스트에서 필요 시 재설정.
    monkeypatch.setattr(chatmod, "classify", lambda t: "stock_analysis")


def test_tool_calls_response_splits_text_and_popups():
    client = _FakeClient(
        [
            _resp(tool_calls=[_tool_call("show_stock_report", {"ticker": "005930"})],
                  finish_reason="tool_calls"),
            _resp(content="삼성전자 리포트를 띄웠습니다. 참고용입니다."),
        ]
    )
    out = chat("삼성전자 어때", _JUDGE, Session(), client=client)

    assert out["popups"][0]["name"] == "show_stock_report"
    assert out["popups"][0]["args"]["ticker"] == "005930"
    assert "삼성전자" in out["text"]
    assert len(client.calls) == 2  # tool_calls → 되먹임 후 최종 답변


def test_no_tool_calls_returns_empty_popups():
    client = _FakeClient([_resp(content="PER은 주가수익비율입니다.")])
    out = chat("설명해줘", _JUDGE, Session(), client=client)
    assert out["popups"] == []
    assert out["text"] == "PER은 주가수익비율입니다."
    assert len(client.calls) == 1


def test_first_create_passes_tools_and_model():
    client = _FakeClient([_resp(content="답변")])
    chat("질문", _JUDGE, Session(), client=client)
    kwargs = client.calls[0]
    assert kwargs["model"] == chatmod.CHAT_MODEL
    assert kwargs["tool_choice"] == "auto"
    assert kwargs["tools"]  # TOOLS 주입
    # gpt-5.6-luna(추론형)+function tools 를 chat/completions 에서 쓰려면 reasoning_effort='none'
    # 이 필요하다(미지정 시 400). CHAT_MODEL_PARAMS 가 매 create 호출에 병합되는지 고정.
    assert kwargs["reasoning_effort"] == "none"
    # 시스템 프롬프트가 매 호출 최신 judgement 로 주입됐는지(첫 메시지=system).
    assert kwargs["messages"][0]["role"] == "system"
    assert _JUDGE["regime"] in kwargs["messages"][0]["content"]


def test_risk_guardrail_blocks_without_calling_llm(monkeypatch):
    monkeypatch.setattr(chatmod, "classify", lambda t: "risk_guardrail")
    client = _FakeClient([])  # 비면 LLM 호출 시 IndexError → 미호출 보장

    out = chat("빚내서 몰빵할까", _JUDGE, Session(), client=client)

    assert out["popups"] == []
    assert client.calls == []  # LLM 미호출(코드가 결정적으로 차단)
    assert out["text"]  # 차단 안내문 존재
    # ③ 위험 조장은 거절이 아니라 위험 환기 + 분산 안내로 방향 전환.
    assert "분산" in out["text"] or "위험" in out["text"]


def test_session_appends_after_normal_chat():
    session = Session()
    client = _FakeClient([_resp(content="설명입니다.")])
    chat("질문", _JUDGE, session, client=client)
    hist = session.history()
    assert hist[-2] == {"role": "user", "content": "질문"}
    assert hist[-1] == {"role": "assistant", "content": "설명입니다."}


def test_session_appends_after_guardrail_block(monkeypatch):
    monkeypatch.setattr(chatmod, "classify", lambda t: "risk_guardrail")
    session = Session()
    out = chat("몰빵", _JUDGE, session, client=_FakeClient([]))
    assert session.history()[-1]["content"] == out["text"]


def test_openai_failure_retries_then_falls_back(monkeypatch):
    calls = {"n": 0}

    def boom(**kwargs):
        calls["n"] += 1
        raise RuntimeError("network")

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=boom))
    )
    out = chat("질문", _JUDGE, Session(), client=client)

    assert calls["n"] == 2  # 1회 재시도
    assert "일시" in out["text"]  # 폴백 안내(크래시 금지)
    assert out["popups"] == []
