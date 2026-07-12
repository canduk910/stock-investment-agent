"""공유 KIS 자격증명 시드 — env→암호화 DB, idempotent, env 없으면 스킵, 실패 graceful."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import auth.kis_seed as seed_mod
import infra.db as infra_db
from auth.kis_store import SHARED_SCOPE, KisCredentialStore
from infra.config import ConfigError, KisConfig
from infra.db import Base, import_models


def _install_memory_db(monkeypatch):
    import_models()
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(infra_db, "get_sessionmaker", lambda: sf)
    return sf


def test_seed_writes_shared_from_env(monkeypatch):
    sf = _install_memory_db(monkeypatch)
    monkeypatch.setattr(
        KisConfig, "load",
        staticmethod(lambda: KisConfig(app_key="ENVk", app_secret="ENVs", env="real", account_no="")),
    )
    monkeypatch.setattr("infra.config.kis_account", lambda: ("12345678", "01"))
    assert seed_mod.seed_shared_kis_from_env() is True
    creds = KisCredentialStore(sf()).get_decrypted(SHARED_SCOPE)
    assert creds.app_key == "ENVk" and creds.account_no == "12345678"


def test_seed_idempotent(monkeypatch):
    sf = _install_memory_db(monkeypatch)
    KisCredentialStore(sf()).upsert_encrypted(SHARED_SCOPE, "EXISTk", "EXISTs", "99999999-01")
    monkeypatch.setattr(
        KisConfig, "load",
        staticmethod(lambda: KisConfig(app_key="ENVk", app_secret="ENVs", env="real", account_no="")),
    )
    monkeypatch.setattr("infra.config.kis_account", lambda: ("12345678", "01"))
    assert seed_mod.seed_shared_kis_from_env() is False  # 이미 있으면 스킵
    assert KisCredentialStore(sf()).get_decrypted(SHARED_SCOPE).app_key == "EXISTk"  # 미변경


def test_seed_skips_without_env(monkeypatch):
    _install_memory_db(monkeypatch)

    def _boom():
        raise ConfigError("KIS_APP_KEY 미설정")

    monkeypatch.setattr(KisConfig, "load", staticmethod(_boom))
    assert seed_mod.seed_shared_kis_from_env() is False  # env 없음 → 스킵(예외 없음)
