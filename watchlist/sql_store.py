"""SqlWatchlistStore — WatchlistStore Protocol 의 SQLAlchemy 구현(유저별 durable).

기존 `WatchlistStore` Protocol(list/get/put/delete/update_target)을 그대로 구현한다 →
service·라우트는 무변경(store 만 스왑). 요청 스코프 Session 을 받아 동작한다(FastAPI get_db).
upsert 는 added_at 을 최초값으로 보존(재등록 시각으로 밀지 않음 — JSON store 와 동일 semantics).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from watchlist.db_models import WatchlistItemRow
from watchlist.models import WatchlistItem


def _to_item(row: WatchlistItemRow) -> WatchlistItem:
    return WatchlistItem(
        user_id=row.user_id,
        ticker=row.ticker,
        stock_name=row.stock_name,
        reason=row.reason,
        target_price=row.target_price,
        added_at=row.added_at,
    )


class SqlWatchlistStore:
    """요청 스코프 Session 기반 워치리스트 저장소(Protocol 구현)."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def _row(self, user_id: str, ticker: str) -> WatchlistItemRow | None:
        return self._db.scalar(
            select(WatchlistItemRow).where(
                WatchlistItemRow.user_id == user_id, WatchlistItemRow.ticker == ticker
            )
        )

    def list_items(self, user_id: str) -> list[WatchlistItem]:
        rows = self._db.scalars(
            select(WatchlistItemRow)
            .where(WatchlistItemRow.user_id == user_id)
            .order_by(WatchlistItemRow.added_at.asc())  # 등록순(registered)
        ).all()
        return [_to_item(r) for r in rows]

    def get(self, user_id: str, ticker: str) -> WatchlistItem | None:
        row = self._row(user_id, ticker)
        return _to_item(row) if row else None

    def put(self, item: WatchlistItem) -> WatchlistItem:
        row = self._row(item.user_id, item.ticker)
        if row is None:  # 신규
            row = WatchlistItemRow(
                user_id=item.user_id,
                ticker=item.ticker,
                stock_name=item.stock_name,
                reason=item.reason,
                target_price=item.target_price,
                added_at=item.added_at,
            )
            self._db.add(row)
        else:  # 갱신(upsert) — added_at 최초값 보존
            row.stock_name = item.stock_name
            row.reason = item.reason
            row.target_price = item.target_price
        self._db.commit()
        return _to_item(row)

    def delete(self, user_id: str, ticker: str) -> None:
        row = self._row(user_id, ticker)
        if row is not None:
            self._db.delete(row)
            self._db.commit()

    def update_target(
        self, user_id: str, ticker: str, target_price: float | None
    ) -> WatchlistItem | None:
        row = self._row(user_id, ticker)
        if row is None:
            return None
        row.target_price = target_price
        self._db.commit()
        return _to_item(row)
