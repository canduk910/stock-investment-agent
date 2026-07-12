"""인증 보안 프리미티브 — bcrypt 비밀번호 해시 + JWT(HS256) 발급/검증.

비밀번호는 **bcrypt 해시만** 저장·검증(평문 저장·로깅 금지). JWT 시크릿은 env `JWT_SECRET`
(미설정 시 개발용 기본값 — 프로덕션은 반드시 설정). 토큰 sub=user_id, exp 로 만료.
GCP 이식성: 관리형 auth 비의존(자체 JWT) → Cloud Run + Cloud SQL 로 무변경.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

_ALGO = "HS256"
# 개발용 기본 시크릿(≥32바이트) — 프로덕션은 env JWT_SECRET 필수. 시크릿 값은 로깅 금지.
_DEV_SECRET = "dev-only-insecure-change-me-in-production-please-set-JWT_SECRET"
_TOKEN_TTL_HOURS = 24 * 7  # 7일


def _secret() -> str:
    return os.environ.get("JWT_SECRET", "").strip() or _DEV_SECRET


def hash_password(password: str) -> str:
    """bcrypt 해시 문자열 반환(솔트 내장). 평문은 저장하지 않는다."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """평문 비밀번호가 해시와 일치하는지. 예외(손상 해시 등)는 False(안전)."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int, *, ttl_hours: int = _TOKEN_TTL_HOURS) -> str:
    """user_id 를 sub 로, exp 만료를 담은 JWT 발급."""
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(hours=ttl_hours)}
    return jwt.encode(payload, _secret(), algorithm=_ALGO)


def decode_token(token: str) -> int | None:
    """JWT 검증 → user_id(int). 만료·서명 오류·형식 오류는 None."""
    try:
        payload = jwt.decode(token, _secret(), algorithms=[_ALGO])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None
