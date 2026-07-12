"""인증 프리미티브 — bcrypt 해시/검증 + JWT 발급/검증(만료·변조 방어)."""
from __future__ import annotations

import time

from auth.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_is_not_plaintext_and_verifies():
    h = hash_password("s3cret-pass")
    assert h != "s3cret-pass"  # 평문 저장 아님
    assert verify_password("s3cret-pass", h) is True
    assert verify_password("wrong", h) is False


def test_hash_is_salted_unique():
    # 같은 비밀번호라도 매번 다른 해시(솔트) — 둘 다 검증은 성공.
    a = hash_password("same")
    b = hash_password("same")
    assert a != b
    assert verify_password("same", a) and verify_password("same", b)


def test_verify_graceful_on_bad_hash():
    assert verify_password("x", "not-a-bcrypt-hash") is False


def test_jwt_roundtrip():
    token = create_access_token(42)
    assert decode_token(token) == 42


def test_jwt_expired_returns_none():
    token = create_access_token(7, ttl_hours=0)  # 즉시 만료
    time.sleep(1)
    assert decode_token(token) is None


def test_jwt_tampered_returns_none():
    token = create_access_token(1)
    assert decode_token(token + "x") is None
    assert decode_token("garbage.token.value") is None
