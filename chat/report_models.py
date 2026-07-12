"""애널리스트/시황 리포트 요약 ORM 모델 — **공동관리(전역 공유, user 무관)**.

네이버 애널리스트 리포트·시황 요약은 모든 유저가 공유하는 공동 데이터라 user_id 가 없다.
scope_key 로 종목(ticker) 요약과 시황(__MARKET__) 요약을 한 테이블에 담는다. (scope_key,
report_id) 유니크 = idempotent(같은 nid 재요약 방지). summary_json 은 검증된 요약 dict.
로컬 SQLite / 프로덕션 GCP Cloud SQL Postgres(JSON→JSONB) 무변경.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from infra.db import Base

MARKET_SCOPE = "__MARKET__"  # 시황(시장 전체) 요약의 scope_key


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AnalystReportRow(Base):
    __tablename__ = "analyst_reports"
    __table_args__ = (
        UniqueConstraint("scope_key", "report_id", name="uq_report_scope_reportid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope_key: Mapped[str] = mapped_column(String(32), index=True, nullable=False)  # ticker | __MARKET__
    report_id: Mapped[str] = mapped_column(String(64), nullable=False)  # 네이버 nid
    broker: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stock_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    summary_json: Mapped[dict] = mapped_column(JSON, nullable=False)  # 검증된 요약 dump
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
