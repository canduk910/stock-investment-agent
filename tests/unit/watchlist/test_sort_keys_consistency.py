"""정렬 키 3중 일관성 — plan §4·§"constants.py".

show_watchlist(LLM-facing SSOT, chat/tools.py) enum ↔ watchlist.constants.SORT_KEYS ↔
(프론트 watchlistLogic.js — vitest에서 별도 검증) 가 일치해야 한다. 하나만 바뀌면
"챗봇은 near_target 정렬을 요청하는데 백엔드는 모른다" 류 불일치가 생긴다.
"""
from __future__ import annotations

from watchlist.constants import SORT_KEYS


def _show_watchlist_enum() -> list[str]:
    """chat/tools.py 의 show_watchlist sort_by enum 을 런타임에 추출(하드코딩 회피)."""
    from chat.tools import TOOLS

    for tool in TOOLS:
        fn = tool.get("function", {})
        if fn.get("name") == "show_watchlist":
            return fn["parameters"]["properties"]["sort_by"]["enum"]
    raise AssertionError("show_watchlist tool not found in chat.tools.TOOLS")


def test_sort_keys_match_show_watchlist_enum():
    assert list(SORT_KEYS) == _show_watchlist_enum()


def test_sort_keys_expected_values():
    # 스펙 고정값(회귀 방어).
    assert list(SORT_KEYS) == ["registered", "change_rate", "near_target"]
