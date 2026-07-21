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


def test_merge_does_not_clobber_manage_watchlist_confirm():
    # manage_watchlist = 사용자가 [확인]해야 반영되는 편집 write 카드. 인텐트 네비 패널(show_watchlist)이
    # 이를 popups[0] 에서 밀어내면 확인 카드가 안 보여 등록/편집 불가(회귀). LLM 이 이 액션 카드를 냈으면
    # 그게 popups[0] 여야 한다 — watchlist_mgmt 인텐트여도 네비 패널을 주입하지 않는다.
    llm = [{"name": "manage_watchlist", "args": {"action": "add", "ticker": "000660", "stock_name": "SK하이닉스"}}]
    out = merge_intent_panel("watchlist_mgmt", llm)
    assert out[0]["name"] == "manage_watchlist"
    assert out == llm  # 인텐트 패널 미주입(액션 카드 보존)


def test_merge_action_panel_wins_over_any_intent_nav():
    # portfolio_advice(→show_balance) 등 다른 네비 인텐트에서도 확인 카드가 우선한다(목표가 편집 등).
    llm = [{"name": "manage_watchlist", "args": {"action": "set_target", "ticker": "005930", "target_price": 90000}}]
    assert merge_intent_panel("portfolio_advice", llm)[0]["name"] == "manage_watchlist"
    assert merge_intent_panel("macro_view", llm)[0]["name"] == "manage_watchlist"


def test_merge_no_mapping_passthrough():
    llm = [{"name": "show_stock_report", "args": {"ticker": "005930"}}]
    assert merge_intent_panel("stock_analysis", llm) == llm  # ticker 필요 → LLM 유지
    assert merge_intent_panel(None, llm) == llm
    assert merge_intent_panel("general_qa", []) == []
