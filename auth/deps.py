"""인증 의존성 — Authorization: Bearer JWT → 현재 User. 유저별 라우트가 이걸로 스코프한다.

`get_current_user`: 헤더의 Bearer 토큰을 검증(decode_token)해 DB 에서 User 를 로드한다. 토큰
부재·무효·유저 없음은 401. 라우트는 `user: User = Depends(get_current_user)` 로 user.id 를 얻는다.
"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from auth.models import User
from auth.security import decode_token
from infra.db import get_db

_UNAUTH = HTTPException(status_code=401, detail="인증이 필요합니다.")


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Bearer JWT → User(없거나 무효면 401). 유저별 라우트의 진입 스코프."""
    token = _bearer_token(authorization)
    if not token:
        raise _UNAUTH
    user_id = decode_token(token)
    if user_id is None:
        raise _UNAUTH
    user = db.get(User, user_id)
    if user is None:
        raise _UNAUTH
    return user


def get_current_user_optional(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User | None:
    """Bearer JWT → User, **없거나 무효면 None(401 안 냄)**.

    공개 유지 라우트(잔고·종목번들·리포트)가 "로그인+등록 시 본인 KIS 키, 아니면 공유 fallback"을
    쓰도록 하는 **옵션 인증**. 토큰 부재·형식오류·만료·유저 없음 모두 None(관대) — 게이트 아님.
    """
    token = _bearer_token(authorization)
    if not token:
        return None
    user_id = decode_token(token)
    if user_id is None:
        return None
    return db.get(User, user_id)
