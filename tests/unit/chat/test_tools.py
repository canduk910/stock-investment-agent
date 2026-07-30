"""팝업 3종 function 스키마 계약 테스트 — llm-safety-guide §2 (프론트 라우팅 계약).

이 스키마의 name·enum·required 는 frontend 팝업 라우팅(QA 경계면 #2·#3)과의 계약이다.
바꾸면 팝업이 조용히 안 뜬다 → 여기서 고정한다. LLM 문체가 아니라 결정적 스키마만 검증.
"""
from __future__ import annotations

from chat.tools import CHAT_MODEL, REPORT_MODEL, CONTENT_TOOLS, TOOLS, run_content_tool


def _tool(name: str) -> dict:
    for t in TOOLS:
        if t["function"]["name"] == name:
            return t["function"]
    raise AssertionError(f"tool {name} 없음")


def _props(name: str) -> dict:
    return _tool(name)["parameters"]["properties"]


def _enum(name: str, param: str) -> list:
    return _props(name)[param]["enum"]


def test_hybrid_model_single_source():
    # 하이브리드(사용자 결정): 일반 대화 = 상위 terra, 리포트·요약·분류·오프라인 = 하위 luna.
    # 두 상수가 모델 ID 단일 출처(문자열 산재 금지). 어느 호출이 어느 상수인지는 chat/CLAUDE.md.
    assert CHAT_MODEL == "gpt-5.6-terra"   # chat()/chat_stream() 일반 대화(사용자 대면)
    assert REPORT_MODEL == "gpt-5.6-luna"  # structured_summary·_reclassify_risk·intent_gen


def test_popup_tool_names__frontend_contract():
    # 표시(팝업) 툴 = 전체 TOOLS − 콘텐츠 툴. 이 집합이 프론트 POPUP_KIND 계약과 일치한다.
    display_names = {t["function"]["name"] for t in TOOLS} - CONTENT_TOOLS
    assert display_names == {
        "show_macro_dashboard",
        "show_stock_report",
        "show_watchlist",
        "manage_watchlist",  # IMP-08: 자연어 워치리스트 편집(추가/제거/목표가)
        "show_balance",  # UX3: 계좌 잔고·평가액·보유종목 현황(파라미터 없음)
        "show_screener",  # 대순환 후보 종목 패널(파라미터 없음) — screen_stocks 추천과 짝
    }


def test_content_tools_defined_in_tools():
    # 콘텐츠 툴(summarize_youtube·search_report)은 실제 TOOLS 에 정의되고 CONTENT_TOOLS 로 표시된다
    # — chat.py(chat·chat_stream)가 이 집합으로 되먹임(실행 vs 팝업)을 분기한다.
    names = {t["function"]["name"] for t in TOOLS}
    assert {"summarize_youtube", "search_report"} <= CONTENT_TOOLS
    assert CONTENT_TOOLS <= names  # 콘텐츠 툴은 전부 실제 TOOLS 스키마로 존재


def test_run_content_tool_search_report_attributes_source(monkeypatch):
    """search_report 콘텐츠 툴 → 리포트 발췌를 출처 귀속 프레이밍으로 되먹인다."""
    monkeypatch.setattr(
        "rag.store.search_reports",
        lambda q, top_k=3: [{"text": "삼성전자 목표가 9만원", "source": "삼성_리포트.pdf", "score": 0.9}],
    )
    out = run_content_tool("search_report", {"query": "목표가"})
    assert "삼성_리포트.pdf" in out and "9만원" in out
    assert "리포트에 따르면" in out  # 출처 귀속·판정 금지 프레이밍


def test_run_content_tool_search_report_empty(monkeypatch):
    monkeypatch.setattr("rag.store.search_reports", lambda q, top_k=3: [])
    out = run_content_tool("search_report", {"query": "x"})
    assert "리포트" in out  # 인덱스 없음 안내(지어내지 않음)


# ── fetch_analyst_reports 콘텐츠 툴(네이버 애널리스트 수집 — 요청 시) ──────────

def test_fetch_analyst_reports_registered_as_content_tool():
    # 챗에서 네이버 애널리스트 리포트를 '수집'하는 콘텐츠 툴. search_report(업로드 PDF RAG)와 별개.
    names = {t["function"]["name"] for t in TOOLS}
    assert "fetch_analyst_reports" in CONTENT_TOOLS
    assert "fetch_analyst_reports" in names


def test_fetch_analyst_reports_ticker_required():
    fn = _tool("fetch_analyst_reports")
    assert fn["parameters"]["required"] == ["ticker"]
    assert "ticker" in _props("fetch_analyst_reports")
    # 설명이 '수집' 용도 + 요청 시만 호출을 명시(오발동 방지).
    desc = fn["description"]
    assert "수집" in desc


def test_run_content_tool_fetch_analyst_attributes_source(monkeypatch):
    """fetch_analyst_reports → 저장된 요약을 출처 귀속 프레이밍으로 되먹인다(판정 아님)."""
    calls = {}

    def fake_fetch(ticker, limit=5, **kw):
        calls["ticker"] = ticker
        calls["limit"] = limit
        return {"fetched": 2, "new": 2, "skipped": 0, "failed": 0}

    monkeypatch.setattr("chat.analyst_service.fetch_and_summarize_for_ticker", fake_fetch)

    class FakeStore:
        def list_reports(self, t):
            return [{
                "broker": "신한투자증권",
                "summary": {"증권사": "신한투자증권", "투자의견": "매수",
                            "목표주가": "9만원", "요약": "메모리 업황 회복 기대"},
            }]

    monkeypatch.setattr("chat.analyst_store.default_store", lambda: FakeStore())

    out = run_content_tool("fetch_analyst_reports", {"ticker": "005930"})
    assert calls["ticker"] == "005930"
    assert "신한투자증권" in out and "매수" in out and "9만원" in out
    assert "리포트에 따르면" in out  # 출처 귀속·판정 금지 프레이밍


def test_run_content_tool_fetch_analyst_bad_ticker_no_fetch(monkeypatch):
    """불량 티커(6자리 아님)면 네이버 수집을 호출하지 않고 graceful 안내."""
    called = {"n": 0}

    def fake_fetch(*a, **k):
        called["n"] += 1
        return {}

    monkeypatch.setattr("chat.analyst_service.fetch_and_summarize_for_ticker", fake_fetch)
    out = run_content_tool("fetch_analyst_reports", {"ticker": "삼성전자"})
    assert "6자리" in out or "확인" in out
    assert called["n"] == 0  # 불량 티커면 수집 미호출(불필요한 크롤 방지)


def test_run_content_tool_fetch_analyst_no_reports_graceful(monkeypatch):
    """수집했지만 리포트 0건이면 지어내지 않고 없음 안내."""
    monkeypatch.setattr(
        "chat.analyst_service.fetch_and_summarize_for_ticker",
        lambda *a, **k: {"fetched": 0, "new": 0, "skipped": 0, "failed": 0},
    )

    class EmptyStore:
        def list_reports(self, t):
            return []

    monkeypatch.setattr("chat.analyst_store.default_store", lambda: EmptyStore())
    out = run_content_tool("fetch_analyst_reports", {"ticker": "058610"})
    assert "찾지 못" in out or "없" in out


def test_all_tools_are_openai_function_type():
    for t in TOOLS:
        assert t["type"] == "function"
        assert "description" in t["function"]
        assert t["function"]["parameters"]["type"] == "object"


def test_show_macro_dashboard_highlight_enum():
    assert _enum("show_macro_dashboard", "highlight") == [
        "regime",
        "cash_ratio",
        "indicators",
    ]


def test_show_stock_report_ticker_required_and_focus_enum():
    fn = _tool("show_stock_report")
    assert fn["parameters"]["required"] == ["ticker"]
    props = fn["parameters"]["properties"]
    assert "ticker" in props and "stock_name" in props
    assert _enum("show_stock_report", "focus") == ["fundamental", "technical", "both"]


def test_show_watchlist_sort_by_enum():
    assert _enum("show_watchlist", "sort_by") == [
        "registered",
        "change_rate",
        "near_target",
    ]


def test_manage_watchlist_action_enum_and_required():
    # 워치리스트 편집(IMP-08): action enum + ticker 필수. 실제 변경은 프론트 confirm 후 반영.
    fn = _tool("manage_watchlist")
    assert fn["parameters"]["required"] == ["action", "ticker"]
    assert _enum("manage_watchlist", "action") == ["add", "remove", "set_target"]
    assert "target_price" in _props("manage_watchlist")


def test_manage_watchlist_has_sell_target_price():
    # 매수/매도 목표가 분리 — set_target 이 매수(target_price)·매도(sell_target_price) 둘 다 수용.
    props = _props("manage_watchlist")
    assert "target_price" in props and "sell_target_price" in props
    # 둘 다 required 는 아님(set_target 시 최소 1개면 됨 — 프론트 popupRouter 가 검증).
    assert "sell_target_price" not in _tool("manage_watchlist")["parameters"]["required"]


def test_show_balance_has_no_parameters():
    # UX3: 잔고 조회는 파라미터 없음(단일 사용자 계좌 — 프론트가 /api/balance 자체조회).
    # LLM 은 "잔고를 띄워라"만 지시하고, 어떤 계좌·필드인지는 코드가 정한다.
    fn = _tool("show_balance")
    params = fn["parameters"]
    assert params["type"] == "object"
    assert params["properties"] == {}
    # required 없음(빈 파라미터) — 있으면 안 됨.
    assert not params.get("required")


def test_show_balance_description_states_when_to_call_and_not():
    # 계좌 잔고·평가액·수익/손실 현황 질문 시 호출 / 리밸런싱·분산 조언·단순질문엔 미호출.
    desc = _tool("show_balance")["description"]
    assert "잔고" in desc
    assert "호출하지 않는다" in desc  # misfire 가드 문구(리밸런싱·분산 조언 제외)


def test_descriptions_state_when_not_to_call__misfire_guard():
    # 각 description 에 "언제 호출/미호출" 모두 명시(오발동 방지, 스킬 §2).
    for name in (
        "show_macro_dashboard",
        "show_stock_report",
        "show_watchlist",
        "manage_watchlist",
        "show_balance",  # UX3: 리밸런싱·분산 조언은 텍스트만 — 미호출 문구 필수.
    ):
        desc = _tool(name)["description"]
        assert "호출하지 않는다" in desc


# ── 대순환 스크리너 콘텐츠 툴(screen_stocks) — 추천은 엔진 귀속·매수 판정 아님 ──────────

def _fake_screener_result():
    return {
        "candidates": [
            {"ticker": "207940", "name": "삼성바이오로직스", "stage": 1, "stage_name": "안정 상승기",
             "arrangement": "단>중>장", "band_width_pct": 2.6, "band_direction": "축소",
             "price": 1000000, "change_rate": 10.0, "market_cap": 700000},
            {"ticker": "005930", "name": "삼성전자", "stage": 4, "stage_name": "안정 하락기",
             "arrangement": "장>중>단", "band_width_pct": -16.9, "band_direction": "확대",
             "price": 78000, "change_rate": -7.5, "market_cap": 14586465},
            {"ticker": "000660", "name": "SK하이닉스", "stage": 6, "stage_name": "상승 진입기",
             "arrangement": "단>장>중", "band_width_pct": 1.2, "band_direction": "확대",
             "price": 180000, "change_rate": -8.3, "market_cap": 12536435},
            {"ticker": "999999", "name": "봉부족주", "stage": None, "stage_name": None,
             "band_width_pct": None, "band_direction": None, "price": 1000, "change_rate": 0, "market_cap": 1000},
        ],
        "catalog": {"periods": {"short": 5, "medium": 20, "long": 40}, "stages": []},
        "market_iscd": "0000", "size": 30, "partial_failure": [], "as_of": "t",
    }


def _patch_screener(monkeypatch, result=None, capture=None):
    monkeypatch.setattr("api.detail._resolve_client", lambda user, db: object())

    def _fake(client, *, market_iscd, size):
        if capture is not None:
            capture.update(market_iscd=market_iscd, size=size)
        return result if result is not None else _fake_screener_result()

    monkeypatch.setattr("stock.screener.screen_grand_cycle", _fake)


def test_screen_stocks_registered_as_content_tool():
    assert "screen_stocks" in CONTENT_TOOLS
    names = {t["function"]["name"] for t in TOOLS}
    assert "screen_stocks" in names  # 실제 TOOLS 스키마로 존재


def test_screen_stocks_default_rising_and_safety_header(monkeypatch):
    _patch_screener(monkeypatch)
    out = run_content_tool("screen_stocks", {"market": "all"})
    # 안전 프레이밍: 엔진 귀속 + 매수 추천 아님 + 면책
    assert "스크리너에 따르면" in out and "매수 추천이 아니다" in out and "면책" in out
    # 기본 상승국면(1·6) → 삼성바이오(1)·SK하이닉스(6) 포함, 하락(4) 삼성전자·판정보류(None) 제외
    assert "삼성바이오로직스" in out and "SK하이닉스" in out
    assert "삼성전자" not in out and "봉부족주" not in out
    # 단계 라벨은 코드(SSOT) — LLM 복제 아님
    assert "안정 상승기" in out and "상승 진입기" in out


def test_screen_stocks_stage_all_shows_down_stage(monkeypatch):
    _patch_screener(monkeypatch)
    out = run_content_tool("screen_stocks", {"market": "all", "stage": "all"})
    assert "삼성전자" in out and "안정 하락기" in out  # 전체 → 하락 단계도 포함


def test_screen_stocks_specific_stage(monkeypatch):
    _patch_screener(monkeypatch)
    out = run_content_tool("screen_stocks", {"stage": "6"})  # 6단계만
    assert "SK하이닉스" in out and "삼성바이오로직스" not in out


def test_screen_stocks_market_mapping(monkeypatch):
    cap = {}
    _patch_screener(monkeypatch, capture=cap)
    run_content_tool("screen_stocks", {"market": "kospi200"})
    assert cap["market_iscd"] == "2001"  # 시장→iscd SSOT


def test_screen_stocks_empty_graceful(monkeypatch):
    _patch_screener(monkeypatch, result={
        "candidates": [], "catalog": None, "market_iscd": "0000", "size": 30,
        "partial_failure": [], "as_of": "t",
    })
    out = run_content_tool("screen_stocks", {})
    assert "지어내" in out  # 없는 종목 날조 금지 안내(graceful)


def test_run_content_tool_threads_user_db_to_impl(monkeypatch):
    # run_content_tool 이 user/db 를 impl(→_resolve_client)로 관통(프로덕션 __shared__ DB 키 필수).
    seen = {}
    monkeypatch.setattr("api.detail._resolve_client",
                        lambda user, db: seen.update(user=user, db=db) or object())
    monkeypatch.setattr("stock.screener.screen_grand_cycle",
                        lambda client, *, market_iscd, size: _fake_screener_result())
    run_content_tool("screen_stocks", {"market": "all"}, user="U", db="DB")
    assert seen == {"user": "U", "db": "DB"}


def test_existing_content_tools_ignore_user_db(monkeypatch):
    # 시그니처 통일(기존 3툴이 user/db 를 받아도 무시) — 하위호환.
    monkeypatch.setattr("rag.store.search_reports", lambda q, top_k=3: [])
    out = run_content_tool("search_report", {"query": "x"}, user="U", db="DB")
    assert isinstance(out, str)  # 크래시 없음
