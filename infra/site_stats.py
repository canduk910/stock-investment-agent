"""사이트 통계 — 가입자수(User 총수) + 방문자수(누적 총 + 오늘 KST).

표시용 **집계만**(개인정보 없음). 방문은 앱 로드 시 1건씩 기록하고, 오늘 카운터는 KST 날짜
경계에서 리셋한다. 단일 싱글턴 행(`id=1`)에 누적/오늘/기준일을 담는다(방문 로그 무한 증가 방지).
"""
from __future__ import annotations

from sqlalchemy import Integer, String, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from infra.db import Base

_SINGLETON_ID = 1


class SiteStat(Base):
    __tablename__ = "site_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # 싱글턴 행(id=1)
    total_visits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 누적 총 방문
    today_visits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 오늘(KST) 방문
    today_date: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 오늘 기준일 KST YYYY-MM-DD


def _today_kst() -> str:
    # 질문 한도와 동일한 KST 오늘(SSOT) — 자정 경계 일관.
    from auth.usage import today_kst

    return today_kst()


def _get_or_create(db: Session) -> SiteStat:
    row = db.get(SiteStat, _SINGLETON_ID)
    if row is None:
        row = SiteStat(id=_SINGLETON_ID, total_visits=0, today_visits=0, today_date=None)
        db.add(row)
    return row


def record_visit(db: Session) -> dict:
    """방문 1건 기록 — 누적 +1, 오늘 카운터는 날짜 경계에서 리셋 후 +1. 반환 {total_visits, today_visits}."""
    row = _get_or_create(db)
    today = _today_kst()
    if row.today_date != today:  # 날짜 경계 → 오늘 카운터 리셋
        row.today_date = today
        row.today_visits = 0
    row.total_visits = (row.total_visits or 0) + 1
    row.today_visits = (row.today_visits or 0) + 1
    db.commit()
    return {"total_visits": row.total_visits, "today_visits": row.today_visits}


def get_site_stats(db: Session) -> dict:
    """표시용 집계 — 가입자수(User 총수) + 방문(누적·오늘). 개인정보 없음.

    오늘 방문은 기준일이 KST 오늘과 다르면 0으로 본다(리셋 전 조회 방어 — 기록 시 리셋과 일관).
    """
    from auth.models import User

    member_count = db.scalar(select(func.count()).select_from(User)) or 0
    row = db.get(SiteStat, _SINGLETON_ID)
    today = _today_kst()
    total = (row.total_visits if row else 0) or 0
    today_v = (row.today_visits if row and row.today_date == today else 0) or 0
    return {
        "member_count": int(member_count),
        "total_visits": int(total),
        "today_visits": int(today_v),
    }
