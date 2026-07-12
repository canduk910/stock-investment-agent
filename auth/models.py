"""User ORM 모델 — 인증·유저별 데이터 스코프의 기준.

비밀번호는 **bcrypt 해시(password_hash)만** 저장한다(평문 금지). email 은 유니크(로그인 식별자).
id 는 유저별 데이터(관심종목·대화기록)의 스코프 키(user_id).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from infra.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # bcrypt 해시만 저장(평문·복호화 불가). 응답/로그에 절대 노출하지 않는다.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
