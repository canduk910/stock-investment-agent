"""KIS 자격증명 해석(본인>공유>env) + 옵션 인증(get_current_user_optional)."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.detail import NoKisCredentials, resolve_kis_client
from auth.deps import get_current_user_optional
from auth.kis_store import SHARED_SCOPE, KisCredentialStore
from auth.models import User
from auth.security import create_access_token
from infra.config import KisConfig
from infra.db import Base, import_models


def _session():
    import_models()
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class _FakeUser:
    def __init__(self, uid):
        self.id = uid


# ── resolve_kis_client 우선순위 ──
def test_resolve_prefers_user_key():
    db = _session()
    store = KisCredentialStore(db)
    store.upsert_encrypted(SHARED_SCOPE, "SHAREDk", "SHAREDs", "99999999-01")
    store.upsert_encrypted("7", "MINEk", "MINEs", "11111111-01")
    r = resolve_kis_client(_FakeUser(7), db)
    assert r.source == "user" and r.cano == "11111111" and r.prdt == "01"
    assert r.client is not None


def test_resolve_falls_back_to_shared_when_no_user_key():
    db = _session()
    KisCredentialStore(db).upsert_encrypted(
        SHARED_SCOPE, "SHAREDk", "SHAREDs", "99999999", acnt_prdt_cd="02"
    )
    r = resolve_kis_client(_FakeUser(7), db)  # 유저 미등록
    assert r.source == "shared" and r.cano == "99999999" and r.prdt == "02"  # prdt 전파


def test_resolve_anonymous_uses_shared():
    db = _session()
    KisCredentialStore(db).upsert_encrypted(SHARED_SCOPE, "SHAREDk", "SHAREDs", "99999999-01")
    r = resolve_kis_client(None, db)  # 비로그인
    assert r.source == "shared"


def test_resolve_env_fallback_when_no_db_creds(monkeypatch):
    db = _session()  # DB 자격증명 없음
    monkeypatch.setattr(
        KisConfig, "load",
        staticmethod(lambda: KisConfig(app_key="ENVk", app_secret="ENVs", env="real", account_no="")),
    )
    monkeypatch.setattr("api.detail.kis_account", lambda: ("55555555", "01"))
    r = resolve_kis_client(_FakeUser(7), db)
    assert r.source == "env" and r.cano == "55555555"


def test_resolve_raises_when_nothing(monkeypatch):
    db = _session()

    def _boom():
        raise RuntimeError("KIS_APP_KEY 미설정")

    monkeypatch.setattr(KisConfig, "load", staticmethod(_boom))
    with pytest.raises(NoKisCredentials):
        resolve_kis_client(_FakeUser(7), db)


# ── get_current_user_optional ──
def test_optional_auth_none_without_token():
    db = _session()
    assert get_current_user_optional(authorization=None, db=db) is None
    assert get_current_user_optional(authorization="Bearer garbage.not.jwt", db=db) is None


def test_optional_auth_returns_user_when_valid():
    db = _session()
    user = User(email="a@example.com", password_hash="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id)
    got = get_current_user_optional(authorization=f"Bearer {token}", db=db)
    assert got is not None and got.id == user.id
