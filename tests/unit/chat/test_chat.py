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


@pytest.fixture(autouse=True)
def _stub_view_context(monkeypatch):
    # 표시 툴 P2 스냅샷 되먹임의 기본값 = 없음(=> tool 결과 {"ok":True}만). 이렇게 해야 표시 툴을
    # 부르는 기존 테스트가 실제 build_view_context(→build_judgement→FRED/KIS, requests_cache 전역
    # 설치로 fred/vix 테스트 오염)를 타지 않는다. 스냅샷 검증 테스트는 개별적으로 재설정한다.
    monkeypatch.setattr(chatmod, "build_view_context", lambda kind, args, **kw: None)


@pytest.fixture(autouse=True)
def _stub_outlook(monkeypatch):
    # 최신 시황 컨텍스트 조회 기본값 = 없음(DB 미접촉). macro_view 주입 테스트만 재설정.
    monkeypatch.setattr(chatmod, "build_recent_outlook_context", lambda **k: None)


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


def test_display_tool_result_passes_user_db(monkeypatch):
    """P2 스냅샷 조립이 user/db 를 build_view_context 로 관통한다(DB KIS 자격증명 사용)."""
    seen = {}
    monkeypatch.setattr(
        chatmod,
        "build_view_context",
        lambda kind, args, *, user=None, db=None: (seen.update(kind=kind, user=user, db=db), "[내 잔고] 순자산 100원")[1],
    )
    out = chatmod._display_tool_result("show_balance", {}, user="U", db="D")
    assert seen == {"kind": "balance", "user": "U", "db": "D"}
    assert "순자산" in out


def test_chat_threads_user_db_to_view_context(monkeypatch):
    """챗 P2 뷰 스냅샷이 로그인 user/db 를 build_view_context 로 관통 → 패널과 동일한 DB KIS 자격증명 사용.
    (프로덕션은 KIS env 를 제거하고 DB(__shared__/유저)에만 seed 하므로, db 미전달 시 env fallback 실패
    = '잔고 일시 조회 불가' 버그. db 를 넘겨야 DB 공유/유저 키로 조회된다.)"""
    seen = {}

    def _spy(kind, args, *, user=None, db=None):
        seen.update(kind=kind, user=user, db=db)
        return "[내 잔고] 순자산 100원"

    monkeypatch.setattr(chatmod, "build_view_context", _spy)
    client = _FakeClient(
        [
            _resp(tool_calls=[_tool_call("show_balance", {})], finish_reason="tool_calls"),
            _resp(content="잔고는 순자산 100원입니다."),
        ]
    )
    out = chat("내 잔고 보여줘", _JUDGE, Session(), client=client, user="U", db="D")
    assert out["popups"][0]["name"] == "show_balance"
    assert seen == {"kind": "balance", "user": "U", "db": "D"}


def test_no_tool_calls_returns_empty_popups():
    client = _FakeClient([_resp(content="PER은 주가수익비율입니다.")])
    out = chat("설명해줘", _JUDGE, Session(), client=client)
    assert out["popups"] == []
    assert out["text"] == "PER은 주가수익비율입니다."
    assert len(client.calls) == 1


def test_content_tool_feeds_transcript_not_popup(monkeypatch):
    """summarize_youtube(콘텐츠 툴) → 자막을 서버가 실행·되먹임(팝업 아님), LLM 이 요약.

    표시 툴({ok:True}+팝업)과 달리 콘텐츠 툴은 실제 텍스트를 2번째 호출 컨텍스트로 되먹인다.
    """
    monkeypatch.setattr("collectors.youtube.fetch_transcript", lambda url, **k: "영상 자막 내용")
    client = _FakeClient(
        [
            _resp(
                tool_calls=[_tool_call("summarize_youtube", {"video_url": "https://youtu.be/x"})],
                finish_reason="tool_calls",
            ),
            _resp(content="영상에 따르면 이런 내용입니다."),
        ]
    )
    out = chat("이 영상 요약해줘 https://youtu.be/x", _JUDGE, Session(), client=client)

    assert out["popups"] == []  # 콘텐츠 툴은 팝업 아님
    assert out["text"] == "영상에 따르면 이런 내용입니다."
    # 2번째 create 의 tool 메시지에 실제 자막이 되먹여졌는지({ok:True} 확인신호가 아니라).
    tool_msgs = [
        m for m in client.calls[1]["messages"]
        if isinstance(m, dict) and m.get("role") == "tool"
    ]
    assert tool_msgs and "영상 자막 내용" in tool_msgs[0]["content"]
    assert '"ok"' not in tool_msgs[0]["content"]


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


# ── 최신 시황 컨텍스트(시장 질문 시 국면 판정과 함께 주입) ──
def test_macro_view_injects_outlook_context(monkeypatch):
    monkeypatch.setattr(chatmod, "classify", lambda t: "macro_view")
    monkeypatch.setattr(
        chatmod, "build_recent_outlook_context", lambda **k: "[시황 리포트 1]\n- 증권사: KB증권"
    )
    client = _FakeClient([_resp(content="지금은 확장 국면이며 시황상 중립입니다.")])
    chat("지금 시장 어때?", _JUDGE, Session(), client=client)
    system_prompt = client.calls[0]["messages"][0]["content"]
    assert "최신 증권사 시황" in system_prompt  # outlook 블록 헤더
    assert "KB증권" in system_prompt  # 시황 내용 주입됨


def test_non_market_intent_skips_outlook_context(monkeypatch):
    monkeypatch.setattr(chatmod, "classify", lambda t: "stock_analysis")

    def _boom(**k):  # 게이팅 검증 — 비-시장 인텐트면 호출조차 안 돼야 한다
        raise AssertionError("outlook context must not be built for non-market intent")

    monkeypatch.setattr(chatmod, "build_recent_outlook_context", _boom)
    client = _FakeClient([_resp(content="삼성전자 설명.")])
    chat("삼성전자 어때", _JUDGE, Session(), client=client)  # _boom 안 나면 게이팅 정상
    assert "최신 증권사 시황" not in client.calls[0]["messages"][0]["content"]


# ── 인텐트 → 우측 패널 결정적 라우팅(원 설계 반영) ──
def test_intent_macro_view_prepends_dashboard_panel(monkeypatch):
    # 인텐트=macro_view + LLM 도구 미호출 → 인텐트가 시장국면 패널을 결정(popups[0]).
    monkeypatch.setattr(chatmod, "classify", lambda t: "macro_view")
    client = _FakeClient([_resp(content="지금은 확장 국면입니다.")])
    out = chat("시장 국면 어때?", _JUDGE, Session(), client=client)
    assert out["popups"][0]["name"] == "show_macro_dashboard"
    assert out["popups"][0]["args"] == {}


def test_intent_watchlist_dedups_llm_duplicate(monkeypatch):
    # 인텐트=watchlist_mgmt + LLM 도 show_watchlist 호출 → 중복 제거(패널 1개).
    monkeypatch.setattr(chatmod, "classify", lambda t: "watchlist_mgmt")
    client = _FakeClient(
        [
            _resp(tool_calls=[_tool_call("show_watchlist", {})], finish_reason="tool_calls"),
            _resp(content="관심종목입니다."),
        ]
    )
    out = chat("관심종목 보여줘", _JUDGE, Session(), client=client)
    assert [p["name"] for p in out["popups"]] == ["show_watchlist"]


def test_intent_panel_applied_even_on_llm_failure(monkeypatch):
    # LLM 전체 실패(폴백)여도 인텐트 네비게이션 패널은 전환된다.
    monkeypatch.setattr(chatmod, "classify", lambda t: "portfolio_advice")
    out = chat("내 잔고 어때?", _JUDGE, Session(), client=_FakeClient([]))  # create → IndexError → 폴백
    assert out["popups"][0]["name"] == "show_balance"


def test_intent_stock_analysis_leaves_llm_panel(monkeypatch):
    # ticker 필요한 종목리포트는 LLM 담당 — 인텐트 패널 주입 없음.
    monkeypatch.setattr(chatmod, "classify", lambda t: "stock_analysis")
    client = _FakeClient(
        [
            _resp(
                tool_calls=[_tool_call("show_stock_report", {"ticker": "005930"})],
                finish_reason="tool_calls",
            ),
            _resp(content="삼성전자 리포트."),
        ]
    )
    out = chat("삼성전자 어때", _JUDGE, Session(), client=client)
    assert out["popups"][0]["name"] == "show_stock_report"  # 인텐트 미개입


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


def test_view_context_tool_feeds_summary_and_keeps_popup(monkeypatch):
    # P2: show_balance 는 여전히 popups(프론트 패널)로 가되, tool 결과에 서버 스냅샷 요약이 실려
    # 같은 턴에 LLM 이 즉답할 수 있다.
    monkeypatch.setattr(chatmod, "build_view_context", lambda kind, args, **kw: "기준시각: T\n순자산 1,900만원")
    client = _FakeClient(
        [
            _resp(tool_calls=[_tool_call("show_balance", {})], finish_reason="tool_calls"),
            _resp(content="순자산 1,900만원입니다."),
        ]
    )
    out = chat("내 잔고 어때", _JUDGE, Session(), client=client)
    # 여전히 팝업(프론트 패널 표시).
    assert any(p["name"] == "show_balance" for p in out["popups"])
    # 2차 호출 메시지의 tool 결과에 스냅샷 요약이 실림.
    tool_msgs = [
        m for m in client.calls[1]["messages"] if isinstance(m, dict) and m.get("role") == "tool"
    ]
    assert any("순자산 1,900만원" in (m.get("content") or "") for m in tool_msgs)


def test_view_context_tool_forwards_ticker(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        chatmod, "build_view_context",
        lambda kind, args, **kw: seen.setdefault("ka", (kind, args)) and None or "기준시각: T\n종목",
    )
    client = _FakeClient(
        [
            _resp(tool_calls=[_tool_call("show_stock_report", {"ticker": "005930"})],
                  finish_reason="tool_calls"),
            _resp(content="삼성전자 현재가는…"),
        ]
    )
    chat("삼성전자 얼마야", _JUDGE, Session(), client=client)
    assert seen["ka"][0] == "stock_report"
    assert seen["ka"][1]["ticker"] == "005930"


def test_non_view_display_tool_no_summary(monkeypatch):
    # 뷰 컨텍스트 툴이 아닌 표시 툴(show_macro_dashboard)은 {"ok":True}만(summary 없음).
    monkeypatch.setattr(chatmod, "build_view_context", lambda kind, args, **kw: "SHOULD NOT APPEAR")
    client = _FakeClient(
        [
            _resp(tool_calls=[_tool_call("show_macro_dashboard", {"highlight": "regime"})],
                  finish_reason="tool_calls"),
            _resp(content="국면 대시보드를 열었습니다."),
        ]
    )
    chat("지금 국면 어때", _JUDGE, Session(), client=client)
    tool_msgs = [
        m for m in client.calls[1]["messages"] if isinstance(m, dict) and m.get("role") == "tool"
    ]
    assert all("SHOULD NOT APPEAR" not in (m.get("content") or "") for m in tool_msgs)


def test_deterministic_keyword_blocks_without_reclassify(monkeypatch):
    # 결정적 위험 키워드("빚내서/몰빵") → LLM 미호출 하드블록. 재분류 미호출.
    called = {"reclassify": 0}
    monkeypatch.setattr(chatmod, "_reclassify_risk", lambda c, q: called.__setitem__("reclassify", called["reclassify"] + 1) or True)
    out = chat("삼성전자 빚내서 몰빵할까", _JUDGE, Session(), client=None)
    assert out["text"] == chatmod._GUARDRAIL_MESSAGE and out["popups"] == []
    assert called["reclassify"] == 0  # 결정적 차단은 재분류 없이


def test_ml_risk_reclassify_confirms_block(monkeypatch):
    # 결정적 키워드 없음 + ML=risk + LLM 재분류=위험 확정 → 차단.
    monkeypatch.setattr(chatmod, "classify", lambda t: "risk_guardrail")
    monkeypatch.setattr(chatmod, "_reclassify_risk", lambda c, q: True)
    client = _FakeClient([])  # 재분류가 mock 이라 LLM 미소비
    out = chat("이 종목 결국 오르는 거 맞지?", _JUDGE, Session(), client=client)
    assert out["text"] == chatmod._GUARDRAIL_MESSAGE and out["popups"] == []


def test_ml_risk_reclassify_allows_proceeds_to_llm(monkeypatch):
    # ML=risk 이지만 LLM 재분류=오탐 → 정상 답변으로 진행(구제).
    monkeypatch.setattr(chatmod, "classify", lambda t: "risk_guardrail")
    monkeypatch.setattr(chatmod, "_reclassify_risk", lambda c, q: False)
    client = _FakeClient([_resp(content="포트폴리오를 살펴보면…")])
    out = chat("내 포트폴리오 조정안 만들어줘", _JUDGE, Session(), client=client)
    assert out["text"] == "포트폴리오를 살펴보면…"  # 차단 아님
    assert out["text"] != chatmod._GUARDRAIL_MESSAGE


def test_reclassify_risk_parses_verdict(monkeypatch):
    # _reclassify_risk 자체 — JSON {block} 파싱. block:true→True, false→False.
    def _client(block):
        return _FakeClient([_resp(content=json.dumps({"block": block}))])

    assert chatmod._reclassify_risk(_client(True), "q") is True
    assert chatmod._reclassify_risk(_client(False), "q") is False


def test_reclassify_risk_defaults_block_on_error():
    # 재분류 LLM 전체 실패 → 보수적 차단(True).
    class _Boom:
        def __init__(self):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._boom))

        def _boom(self, **kw):
            raise Exception("openai down")

    assert chatmod._reclassify_risk(_Boom(), "q") is True


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
