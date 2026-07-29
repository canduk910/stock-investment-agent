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
from watchlist.store import _UNSET  # 부분 갱신 sentinel(단일 출처)


def _to_item(row: WatchlistItemRow) -> WatchlistItem:
    """SQLAlchemy Row → Pydantic WatchlistItem(service·라우트가 소비하는 도메인 모델).

    JSON store 와 동일한 WatchlistItem 을 반환해야 store 를 스왑해도 상위 계약이 불변이다.
    """
    return WatchlistItem(
        user_id=row.user_id,
        ticker=row.ticker,
        stock_name=row.stock_name,
        reason=row.reason,
        target_price=row.target_price,
        sell_target_price=row.sell_target_price,
        added_at=row.added_at,
    )


class SqlWatchlistStore:
    """요청 스코프 Session 기반 워치리스트 저장소(Protocol 구현)."""

    def __init__(self, db: Session) -> None:
        # 요청 스코프 Session(FastAPI get_db 주입) — 이 store 는 요청 수명 동안만 산다.
        self._db = db

    def _row(self, user_id: str, ticker: str) -> WatchlistItemRow | None:
        """(user_id, ticker) 복합키로 단건 조회 — 유니크 제약과 짝(모든 CRUD 의 진입점)."""
        return self._db.scalar(
            select(WatchlistItemRow).where(
                WatchlistItemRow.user_id == user_id, WatchlistItemRow.ticker == ticker
            )
        )

    def list_items(self, user_id: str) -> list[WatchlistItem]:
        # 등록순(added_at 오름차순) 고정 — 다른 정렬은 프론트(watchlistLogic.js)가 순수 계산한다.
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
        # 신규 insert vs 기존 갱신(upsert)을 (user_id,ticker) 존재로 결정.
        row = self._row(item.user_id, item.ticker)
        if row is None:  # 신규
            row = WatchlistItemRow(
                user_id=item.user_id,
                ticker=item.ticker,
                stock_name=item.stock_name,
                reason=item.reason,
                target_price=item.target_price,
                sell_target_price=item.sell_target_price,
                added_at=item.added_at,
            )
            self._db.add(row)
        else:  # 갱신(upsert) — added_at 최초값 보존
            # added_at 은 일부러 안 건드린다 — 재등록해도 최초 등록 시각을 유지(정렬 안정).
            row.stock_name = item.stock_name
            row.reason = item.reason
            row.target_price = item.target_price
            row.sell_target_price = item.sell_target_price
        self._db.commit()
        return _to_item(row)

    def delete(self, user_id: str, ticker: str) -> None:
        # 없는 종목 delete 는 조용히 no-op(멱등). 있으면 행 삭제 후 commit.
        row = self._row(user_id, ticker)
        if row is not None:
            self._db.delete(row)
            self._db.commit()

    def update_targets(
        self, user_id, ticker, *, target_price=_UNSET, sell_target_price=_UNSET
    ) -> WatchlistItem | None:
        """매수/매도 목표가 부분 갱신. `_UNSET`=미제공(불변), `None`=해제. 미등록이면 None.

        PATCH 가 준 side 만 넘어오므로(매도만 보내면 매수는 `_UNSET`), 각 필드를
        `is not _UNSET` 로 검사해 **넘어온 값만** 덮는다 — 안 넘어온 side 는 기존값 보존.
        """
        row = self._row(user_id, ticker)
        if row is None:
            return None
        # `is not _UNSET` — None(해제)과 미제공(불변)을 구분하는 핵심 sentinel 비교.
        if target_price is not _UNSET:
            row.target_price = target_price
        if sell_target_price is not _UNSET:
            row.sell_target_price = sell_target_price
        self._db.commit()
        return _to_item(row)

    def update_target(
        self, user_id: str, ticker: str, target_price: float | None
    ) -> WatchlistItem | None:
        """(하위호환) 매수 목표가만 갱신 — update_targets 로 위임(신규 코드는 update_targets 사용)."""
        return self.update_targets(user_id, ticker, target_price=target_price)
