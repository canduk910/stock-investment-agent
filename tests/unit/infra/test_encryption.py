"""KIS 자격증명 암호화(Fernet) — 왕복·위변조 감지·마스킹·키 스왑."""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from infra import encryption


def test_encrypt_decrypt_roundtrip():
    plain = "PSxxxxxxAPPKEY1234567890"
    token = encryption.encrypt(plain)
    assert token != plain  # 실제 암호문(평문 아님)
    assert encryption.decrypt(token) == plain


def test_encrypt_is_non_deterministic():
    # Fernet은 타임스탬프/IV 포함 → 같은 입력도 매번 다른 암호문(둘 다 복호화 가능).
    a = encryption.encrypt("secret")
    b = encryption.encrypt("secret")
    assert a != b
    assert encryption.decrypt(a) == encryption.decrypt(b) == "secret"


def test_decrypt_tampered_raises():
    token = encryption.encrypt("secret")
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(Exception):  # InvalidToken(HMAC 검증 실패)
        encryption.decrypt(tampered)


def test_key_swap_via_env(monkeypatch):
    # KIS_ENC_KEY 로 마스터키 스왑 — 다른 키로 암호화한 토큰은 기본키로 복호화 불가.
    other = Fernet.generate_key().decode()
    monkeypatch.setenv("KIS_ENC_KEY", other)
    token = encryption.encrypt("hello")
    assert encryption.decrypt(token) == "hello"
    monkeypatch.delenv("KIS_ENC_KEY", raising=False)
    with pytest.raises(Exception):  # 기본(dev) 키로는 복호화 불가
        encryption.decrypt(token)


def test_mask_hides_middle():
    assert encryption.mask("PSABCDEFGH12", keep=2) == "PS••••12"
    assert encryption.mask("12345678", keep=2) == "12••••78"


def test_mask_short_and_empty():
    assert encryption.mask("ab", keep=2) == "••"  # 짧으면 전체 마스킹
    assert encryption.mask("", keep=2) == ""
    assert encryption.mask(None, keep=2) == ""
