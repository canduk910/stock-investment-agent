"""인텐트 → 우측 패널 결정적 라우팅(최초 설계). 매핑·prepend·dedup·SSOT 정합·안전.

인텐트가 인자 없는 네비게이션 패널(시장국면/관심종목/잔고)을 결정적으로 선택한다. 편집·매매 패널은
절대 매핑하지 않는다(오분류가 편집/주문 유발 0). 값은 tools.py 표시 툴과 정합.
"""
from __future__ import annotations

from chat.intent import LABELS
from chat.intent_panel import INTENT_PANEL, intent_panel_name, merge_intent_panel
from chat.tools import CONTENT_TOOLS, TOOLS

_DISPLAY_TOOLS = {t["function"]["name"] for t in TOOLS} - set(CONTENT_TOOLS)


def test_mapping_is_navigation_labels_only():
    assert INTENT_PANEL == {
        "macro_view": "show_macro_dashboard",
        "watchlist_mgmt": "show_watchlist",
        "portfolio_advice": "show_balance",
    }
    # ticker 필요/편집/일반/위험 라벨은 매핑 없음(LLM 담당 or 패널 없음).
    for lbl in ("stock_analysis", "analyst_report", "general_qa", "risk_guardrail"):
        assert intent_panel_name(lbl) is None


def test_mapping_keys_are_valid_intent_labels():
    for lbl in INTENT_PANEL:
        assert lbl in LABELS


def test_mapping_values_are_display_tools_not_content():
    # 값(툴명)은 tools.py 표시 툴이어야 popupRouter 로 라우팅되고, 콘텐츠 툴이면 안 된다(SSOT 정합).
    for tool in INTENT_PANEL.values():
        assert tool in _DISPLAY_TOOLS
        assert tool not in CONTENT_TOOLS
    # 편집·매매 패널은 절대 매핑하지 않는다(인텐트 오분류가 편집/주문을 유발하지 않도록).
    assert "manage_watchlist" not in INTENT_PANEL.values()


def test_merge_prepends_intent_panel_when_empty():
    assert merge_intent_panel("macro_view", []) == [{"name": "show_macro_dashboard", "args": {}}]


def test_merge_dedups_llm_duplicate_keeps_others():
    llm = [
        {"name": "show_macro_dashboard", "args": {"x": 1}},  # LLM 중복(같은 패널)
        {"name": "show_watchlist", "args": {}},
    ]
    out = merge_intent_panel("macro_view", llm)
    assert out[0] == {"name": "show_macro_dashboard", "args": {}}  # 인텐트 패널이 맨 앞
    assert {"name": "show_macro_dashboard", "args": {"x": 1}} not in out  # 중복 제거
    assert {"name": "show_watchlist", "args": {}} in out  # 다른 팝업 보존


def test_merge_intent_wins_over_conflicting_llm_panel():
    # popups[0] = 인텐트 패널 → 프론트가 popups[0] 로 전환하므로 인텐트가 우선.
    out = merge_intent_panel("watchlist_mgmt", [{"name": "show_stock_report", "args": {"ticker": "005930"}}])
    assert out[0]["name"] == "show_watchlist"


def test_merge_no_mapping_passthrough():
    llm = [{"name": "show_stock_report", "args": {"ticker": "005930"}}]
    assert merge_intent_panel("stock_analysis", llm) == llm  # ticker 필요 → LLM 유지
    assert merge_intent_panel(None, llm) == llm
    assert merge_intent_panel("general_qa", []) == []
