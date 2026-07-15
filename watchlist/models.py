"""워치리스트 항목 모델 — plan §"watchlist/models.py".

Pydantic(v2). ticker 정규식은 frontend/src/lib/ticker.js SSOT(`^[0-9A-Za-z]{6}$`)와 동일 —
백엔드/프론트가 같은 규칙을 공유(불일치 시 "직접입력은 받는데 팝업은 거부" UX 붕괴).
target_price 는 옵션이며 음수 거부(≥0). added_at 은 ISO8601 문자열(라우트가 주입).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from watchlist.constants import DEFAULT_USER_ID

# ticker.js 와 동일 — 6자 영숫자. numeric 강제가 아니라 명백한 불량(종목명·부분입력) 차단.
TICKER_PATTERN = r"^[0-9A-Za-z]{6}$"


class WatchlistItem(BaseModel):
    """관심종목 1건(저장 계약). DynamoDB (user_id, ticker) = PK/SK 대응."""

    user_id: str = DEFAULT_USER_ID
    ticker: str = Field(pattern=TICKER_PATTERN)
    stock_name: str
    reason: str | None = None
    target_price: float | None = Field(default=None, ge=0)  # 매수 목표가('사고 싶은 가격')
    sell_target_price: float | None = Field(default=None, ge=0)  # 매도 목표가('팔고 싶은 가격')
    added_at: str  # ISO8601(datetime.now(timezone.utc).isoformat())
