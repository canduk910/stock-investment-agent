"""유저별 KIS 자격증명 ORM — **Fernet 암호문만** 저장(평문 금지).

scope_key = str(user.id)(본인 등록) 또는 "__shared__"(공유 fallback, 미등록/비로그인용).
현재가 무캐시 원칙과 무관(시세가 아닌 사용자 durable 자격증명). 복호화는 store 에서만.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from infra.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class KisCredentialRow(Base):
    __tablename__ = "kis_credentials"
    __table_args__ = (UniqueConstraint("scope_key", name="uq_kis_scope"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope_key: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    app_key_enc: Mapped[str] = mapped_column(String(512), nullable=False)
    app_secret_enc: Mapped[str] = mapped_column(String(512), nullable=False)
    account_no_enc: Mapped[str | None] = mapped_column(String(256), nullable=True)  # CANO(암호문)
    acnt_prdt_cd: Mapped[str] = mapped_column(String(8), default="01", nullable=False)
    env: Mapped[str] = mapped_column(String(8), default="real", nullable=False)  # real | demo
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )
