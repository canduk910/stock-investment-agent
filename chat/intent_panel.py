"""인텐트 → 우측 패널 결정적 라우팅 (최초 설계 반영).

인텐트 분류기(`chat/intent.py::classify`)가 낸 라벨을 **인자 없는 네비게이션 패널**로 직접 매핑한다.
LLM function calling 과 별개로, 인텐트가 이 3개 패널을 **결정적으로** 선택한다 — `merge_intent_panel`이
인텐트 패널을 popups **맨 앞**에 주입하고, 프론트는 `popups[0]`으로 우측 패널을 전환하므로 인텐트가
권위적으로 패널을 결정한다.

ticker 가 필요한 종목리포트(`stock_analysis`/`analyst_report`)와 args 가 필요한 편집(`manage_watchlist`)은
인텐트가 인자를 뽑을 수 없어 **매핑하지 않고 LLM 이 담당**한다. `general_qa`/`risk_guardrail`은 패널 없음.
**편집·매매 패널은 절대 매핑하지 않는다** — 인텐트 오분류가 편집/주문을 유발하지 않도록 조회/표시 패널만.

값(툴명)은 `chat/tools.py`의 표시 툴이자 frontend `popupRouter.POPUP_KIND` 키와 일치한다(SSOT).
"""
from __future__ import annotations

# 인텐트 라벨 → 표시 툴명(= 우측 패널). 인자 없는 네비게이션 3종만(나머지 라벨은 매핑 없음 = LLM/패널 없음).
INTENT_PANEL: dict[str, str] = {
    "macro_view": "show_macro_dashboard",  # 시장 국면 대시보드
    "watchlist_mgmt": "show_watchlist",  # 관심종목
    "portfolio_advice": "show_balance",  # 내 잔고
}


# 사용자가 [확인]을 눌러야 반영되는 편집 write 카드(SSOT: frontend ManageWatchlistConfirm). 인텐트 네비
# 패널이 이 카드를 popups[0]에서 밀어내면 확인 카드가 안 보여 등록/편집이 불가능하다 → 인텐트 주입 예외.
_ACTION_PANELS = frozenset({"manage_watchlist"})

# 대순환 후보 종목 패널(show_screener)이 이미 있으면(=screen_stocks 콘텐츠 툴이 돈 턴, `with_screener_panel`)
# 인텐트 네비 패널로 덮지 않는다 — "종목 추천/후보종목 확인" 이 portfolio_advice 로 분류돼 잔고(show_balance)
# 패널이 후보 종목 답변 위에 뜨던 문제 해소. 추천 답변과 패널을 일치시킨다(엔진 산출·매수 추천 아님 불변).
_SCREENER_PANEL = "show_screener"
_SCREENER_CONTENT_TOOL = "screen_stocks"


def intent_panel_name(intent: str | None) -> str | None:
    """인텐트 라벨 → 표시 툴명(패널). 매핑 없으면 None(패널 없음 / LLM 담당)."""
    return INTENT_PANEL.get(intent or "")


def merge_intent_panel(intent: str | None, popups: list[dict]) -> list[dict]:
    """인텐트가 정하는 네비게이션 패널을 popups **맨 앞에 주입**(중복 제거).

    프론트가 `popups[0]`로 우측 패널을 전환하므로, 인텐트 패널을 맨 앞에 두면 인텐트가 **권위적**으로
    패널을 결정한다(원 설계). LLM 이 같은 패널을 이미 냈으면 중복 제거하고, 다른 **네비** 패널을 냈어도
    인텐트 패널이 앞이라 우선한다. 인텐트 매핑이 없으면 popups 그대로(LLM 결정 유지).

    **예외**: LLM 이 편집 확인 카드(`manage_watchlist`)를 냈으면 인텐트 네비 패널을 주입하지 않는다 —
    이 카드는 사용자가 [확인]해야 반영되는 write 액션이라, 네비 패널이 가리면 등록/편집이 불가능하다
    (예: "SK하이닉스 관심종목 추가" → watchlist_mgmt 인텐트가 show_watchlist 를 앞에 밀어 확인 카드가
    안 뜨던 회귀). 액션 카드가 있으면 LLM popups 순서를 그대로 보존한다.
    """
    base = popups if isinstance(popups, list) else []
    name = intent_panel_name(intent)
    if not name:
        return list(base)
    if any(
        isinstance(p, dict) and p.get("name") in (_ACTION_PANELS | {_SCREENER_PANEL})
        for p in base
    ):
        return list(base)  # 확인·편집 액션 카드 / 후보 종목 패널 보존(popups[0] 유지)
    deduped = [p for p in base if isinstance(p, dict) and p.get("name") != name]
    return [{"name": name, "args": {}}] + deduped


def with_screener_panel(popups: list[dict], tool_names) -> list[dict]:
    """`screen_stocks` 콘텐츠 툴이 호출된 턴이면 후보 종목 패널(show_screener)을 popups **맨 앞**에 보강한다.

    콘텐츠 툴은 팝업이 아니라 텍스트만 되먹이므로(추천을 글로만 줌), 같은 후보를 시각적으로 보여주는
    show_screener 패널을 결정적으로 함께 열어 답변과 화면을 일치시킨다(LLM 이 별도 툴을 안 불러도 열림).
    맨 앞에 두어 `merge_intent_panel` 의 잔고 등 인텐트 네비 주입을 억제한다(위 `_SCREENER_PANEL` 예외).
    이미 show_screener 가 있으면(LLM 이 직접 호출) 중복 없이 맨 앞으로 정렬.
    """
    base = list(popups) if isinstance(popups, list) else []
    if _SCREENER_CONTENT_TOOL not in set(tool_names or ()):
        return base
    deduped = [p for p in base if not (isinstance(p, dict) and p.get("name") == _SCREENER_PANEL)]
    return [{"name": _SCREENER_PANEL, "args": {}}] + deduped
