"""워치리스트 ORM 모델 — 유저별 durable 저장(SQLite 로컬 / GCP Cloud SQL Postgres).

`(user_id, ticker)` 유니크 = 기존 JSON store 의 PK/SK 계약 그대로(스왑만). user_id 는 인증된
User.id(문자열화). 캐시 아님(현재가 무캐시는 시세 경로, 여기는 사용자 등록 데이터).
"""
from __future__ import annotations

from sqlalchemy import Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from infra.db import Base


class WatchlistItemRow(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("user_id", "ticker", name="uq_watchlist_user_ticker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    stock_name: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    added_at: Mapped[str] = mapped_column(String(40), nullable=False)  # ISO8601
