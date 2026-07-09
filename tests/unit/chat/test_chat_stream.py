"""chat_stream() 제너레이터 + tool_calls 재조립 테스트 — 계획 §백엔드(OpenAI stream mock).

기존 chat()과 나란히 추가되는 스트리밍 경로. LLM 출력 자체는 비결정적이라 대상 아님.
결정적 부분만 검증한다:
- guardrail 은 LLM 미호출·차단 token·done(popups=[])  (코드가 결정적으로 차단, 안전 원칙)
- 툴 없는 답변: content 델타 → token 이벤트 누적 = 전체 text, done(popups=[]), session.append
- 툴 답변: 스트리밍 tool_calls 델타(index별 name/arguments 조각)를 _accumulate_tool_calls 로
  재조립해 popups 정확 → 이후 narration 토큰 스트림 → done(popups=[...])
- 예외 → _FALLBACK_MESSAGE token + done (크래시 금지, 폴백 정신)

경계(OpenAI 클라이언트)만 mock 하고 재조립·조립 로직은 실제 코드를 통과시킨다.
FakeClient 는 stream=True 일 때 델타 청크를 yield 하는 이터레이터를 반환한다.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import chat.chat as chatmod
from chat.chat import _accumulate_tool_calls, chat_stream
from chat.session import Session
from macro.engine import judge_regime

_JUDGE = judge_regime({"yield_spread": 0.6, "hy_spread": 2.0, "vix": 12.0})


# --- 스트리밍 청크 헬퍼: OpenAI 스트림 델타 shape 을 흉내낸다 ---
def _content_chunk(text, finish_reason=None):
    delta = SimpleNamespace(content=text, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)])


def _tool_delta(index, *, tc_id=None, name=None, args=None):
    """tool_calls 델타 조각 하나(하나의 index 에 대해 name 또는 args 조각을 실어 보낸다)."""
    fn = SimpleNamespace(name=name, arguments=args)
    return SimpleNamespace(index=index, id=tc_id, function=fn)


def _tool_chunk(tool_deltas, finish_reason=None):
    delta = SimpleNamespace(content=None, tool_calls=tool_deltas)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)])


class _FakeStreamClient:
    """create() 호출마다 준비된 청크 이터러블을 순서대로 반환(호출 kwargs 기록)."""

    def __init__(self, streams):
        self._streams = list(streams)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return iter(self._streams.pop(0))


@pytest.fixture(autouse=True)
def _no_guardrail(monkeypatch):
    # 기본은 비위험 라벨(LLM 경로). 개별 테스트에서 재설정.
    monkeypatch.setattr(chatmod, "classify", lambda t: "stock_analysis")


def _collect(gen):
    return list(gen)


# --- _accumulate_tool_calls: 재조립 순수 로직 ---
def test_accumulate_tool_calls_reassembles_name_and_args_fragments():
    # 하나의 tool_call 이 여러 델타로 쪼개져 도착: id·name 한 조각, arguments 여러 조각.
    deltas_per_chunk = [
        [_tool_delta(0, tc_id="call_1", name="show_stock_report", args="")],
        [_tool_delta(0, args='{"tick')],
        [_tool_delta(0, args='er": "0059')],
        [_tool_delta(0, args='30"}')],
    ]
    popups = _accumulate_tool_calls(deltas_per_chunk)
    assert popups == [{"name": "show_stock_report", "args": {"ticker": "005930"}}]


def test_accumulate_tool_calls_handles_multiple_indices():
    deltas_per_chunk = [
        [
            _tool_delta(0, tc_id="c0", name="show_macro_dashboard", args="{}"),
            _tool_delta(1, tc_id="c1", name="show_watchlist", args=""),
        ],
        [_tool_delta(1, args='{"sort_by": "near_target"}')],
    ]
    popups = _accumulate_tool_calls(deltas_per_chunk)
    assert popups[0]["name"] == "show_macro_dashboard"
    assert popups[1] == {"name": "show_watchlist", "args": {"sort_by": "near_target"}}


def test_accumulate_tool_calls_bad_json_yields_empty_args():
    deltas_per_chunk = [[_tool_delta(0, tc_id="c0", name="show_watchlist", args="{not json")]]
    popups = _accumulate_tool_calls(deltas_per_chunk)
    assert popups == [{"name": "show_watchlist", "args": {}}]


# --- guardrail: LLM 미호출 결정적 차단 ---
def test_guardrail_blocks_without_calling_llm(monkeypatch):
    monkeypatch.setattr(chatmod, "classify", lambda t: "risk_guardrail")
    client = _FakeStreamClient([])  # 비면 LLM 호출 시 IndexError → 미호출 보장
    session = Session()

    events = _collect(chat_stream("빚내서 몰빵할까", _JUDGE, session, client=client))

    assert client.calls == []  # LLM 미호출(코드가 결정적으로 차단)
    types = [e["type"] for e in events]
    assert types[0] == "stage" and events[0]["stage"] == "analyze"
    # 차단문 token 존재
    token_text = "".join(e["text"] for e in events if e["type"] == "token")
    assert token_text
    assert "분산" in token_text or "위험" in token_text
    # 마지막은 done, popups 비어있음
    assert events[-1] == {"type": "done", "popups": []}
    # 세션에 차단문 append
    assert session.history()[-1]["content"] == token_text


# --- 툴 없는 답변: token 누적 = 전체 text ---
def test_no_tool_calls_streams_tokens_and_appends_session():
    stream = [
        _content_chunk("PER은 "),
        _content_chunk("주가수익"),
        _content_chunk("비율입니다.", finish_reason="stop"),
    ]
    client = _FakeStreamClient([stream])
    session = Session()

    events = _collect(chat_stream("설명해줘", _JUDGE, session, client=client))

    tokens = [e["text"] for e in events if e["type"] == "token"]
    assert "".join(tokens) == "PER은 주가수익비율입니다."
    assert events[-1] == {"type": "done", "popups": []}
    # 첫 호출은 stream=True, tools 주입
    assert client.calls[0]["stream"] is True
    assert client.calls[0]["tools"]
    assert client.calls[0]["model"] == "gpt-5.4"
    # 누적 text 로 세션 append
    assert session.history()[-1]["content"] == "PER은 주가수익비율입니다."
    assert session.history()[-2]["content"] == "설명해줘"


# --- 툴 답변: 재조립 popups + narration 토큰 ---
def test_tool_calls_stream_emits_popups_then_narration():
    call1 = [
        _tool_chunk([_tool_delta(0, tc_id="c0", name="show_stock_report", args="")]),
        _tool_chunk([_tool_delta(0, args='{"ticker": ')]),
        _tool_chunk([_tool_delta(0, args='"005930"}')], finish_reason="tool_calls"),
    ]
    call2 = [
        _content_chunk("삼성전자 "),
        _content_chunk("리포트를 띄웠습니다.", finish_reason="stop"),
    ]
    client = _FakeStreamClient([call1, call2])
    session = Session()

    events = _collect(chat_stream("삼성전자 어때", _JUDGE, session, client=client))

    # popups 이벤트가 재조립돼 정확히 나온다
    popup_events = [e for e in events if e["type"] == "popups"]
    assert popup_events
    assert popup_events[0]["popups"] == [
        {"name": "show_stock_report", "args": {"ticker": "005930"}}
    ]
    # narration 토큰이 popups 이후에 스트리밍된다
    narration = "".join(e["text"] for e in events if e["type"] == "token")
    assert narration == "삼성전자 리포트를 띄웠습니다."
    # done 에 최종 popups
    assert events[-1]["type"] == "done"
    assert events[-1]["popups"] == [
        {"name": "show_stock_report", "args": {"ticker": "005930"}}
    ]
    assert len(client.calls) == 2  # 호출#1 tool_calls → 호출#2 narration
    assert client.calls[1]["stream"] is True
    # 세션엔 narration 누적
    assert session.history()[-1]["content"] == "삼성전자 리포트를 띄웠습니다."


def test_generate_stage_emitted_before_tokens():
    stream = [_content_chunk("답변", finish_reason="stop")]
    client = _FakeStreamClient([stream])
    events = _collect(chat_stream("질문", _JUDGE, Session(), client=client))
    stages = [e["stage"] for e in events if e["type"] == "stage"]
    # analyze → generate 순서(regime 은 라우트에서 주입, chat_stream 은 generate 부터)
    assert "generate" in stages
    gen_idx = next(i for i, e in enumerate(events) if e.get("stage") == "generate")
    first_token_idx = next(i for i, e in enumerate(events) if e["type"] == "token")
    assert gen_idx < first_token_idx


# --- 예외 → 폴백 ---
def test_exception_falls_back_to_fallback_message(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("network")

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=boom)))
    session = Session()

    events = _collect(chat_stream("질문", _JUDGE, session, client=client))

    token_text = "".join(e["text"] for e in events if e["type"] == "token")
    assert "일시" in token_text  # 폴백 안내
    assert events[-1] == {"type": "done", "popups": []}
    assert session.history()[-1]["content"] == token_text
