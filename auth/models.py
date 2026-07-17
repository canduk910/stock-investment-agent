"""User ORM 모델 — 인증·유저별 데이터 스코프의 기준.

비밀번호는 **bcrypt 해시(password_hash)만** 저장한다(평문 금지). email 은 유니크(로그인 식별자).
id 는 유저별 데이터(관심종목·대화기록)의 스코프 키(user_id).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from infra.db import Base

# 관리자 제외 계정의 하루 질문 한도 기본값(대략 20회). 관리자는 무제한.
DEFAULT_DAILY_LIMIT = 20


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # bcrypt 해시만 저장(평문·복호화 불가). 응답/로그에 절대 노출하지 않는다.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    # 권한(RBAC) — 관리자만 유저 관리·통계·한도 제어. 기본 False.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 토큰 사용량 한도(질문 횟수 기반, 매일 리셋). 관리자는 무제한(면제).
    daily_limit: Mapped[int] = mapped_column(Integer, default=DEFAULT_DAILY_LIMIT, nullable=False)
    used_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 오늘 사용한 질문 수
    usage_date: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 집계 기준일(KST YYYY-MM-DD)
    total_questions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 누적 질문 수(통계)
