"""팝업 3종 function 스키마 계약 테스트 — llm-safety-guide §2 (프론트 라우팅 계약).

이 스키마의 name·enum·required 는 frontend 팝업 라우팅(QA 경계면 #2·#3)과의 계약이다.
바꾸면 팝업이 조용히 안 뜬다 → 여기서 고정한다. LLM 문체가 아니라 결정적 스키마만 검증.
"""
from __future__ import annotations

from chat.tools import CHAT_MODEL, TOOLS


def _tool(name: str) -> dict:
    for t in TOOLS:
        if t["function"]["name"] == name:
            return t["function"]
    raise AssertionError(f"tool {name} 없음")


def _props(name: str) -> dict:
    return _tool(name)["parameters"]["properties"]


def _enum(name: str, param: str) -> list:
    return _props(name)[param]["enum"]


def test_chat_model_is_gpt_5_4__single_source():
    # 사용자 결정: 모델은 gpt-5.4. 이 상수가 모델 ID 단일 출처(문자열 산재 금지).
    assert CHAT_MODEL == "gpt-5.4"


def test_popup_tool_names__frontend_contract():
    names = {t["function"]["name"] for t in TOOLS}
    assert names == {
        "show_macro_dashboard",
        "show_stock_report",
        "show_watchlist",
        "manage_watchlist",  # IMP-08: 자연어 워치리스트 편집(추가/제거/목표가)
    }


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


def test_descriptions_state_when_not_to_call__misfire_guard():
    # 각 description 에 "언제 호출/미호출" 모두 명시(오발동 방지, 스킬 §2).
    for name in ("show_macro_dashboard", "show_stock_report", "show_watchlist", "manage_watchlist"):
        desc = _tool(name)["description"]
        assert "호출하지 않는다" in desc
