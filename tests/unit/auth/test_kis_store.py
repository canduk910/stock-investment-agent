"""유저별 KIS 자격증명 스토어 — 암호화 저장·해석(user>__shared__)·마스킹 상태·삭제."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth.kis_store import SHARED_SCOPE, KisCredentialStore
from infra.db import Base, import_models


def _session():
    import_models()
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_upsert_roundtrip_encrypts_at_rest():
    db = _session()
    store = KisCredentialStore(db)
    store.upsert_encrypted("7", "APPKEYplain", "APPSECRETplain", "12345678-01")
    creds = store.get_decrypted("7")
    assert creds.app_key == "APPKEYplain" and creds.app_secret == "APPSECRETplain"
    assert creds.account_no == "12345678" and creds.acnt_prdt_cd == "01"  # 하이픈 파싱
    # DB 행엔 암호문만(평문 미저장)
    from auth.kis_models import KisCredentialRow
    from sqlalchemy import select
    row = db.scalar(select(KisCredentialRow).where(KisCredentialRow.scope_key == "7"))
    assert "APPKEYplain" not in row.app_key_enc
    assert "APPSECRETplain" not in row.app_secret_enc


def test_resolve_prefers_user_then_shared():
    db = _session()
    store = KisCredentialStore(db)
    store.upsert_encrypted(SHARED_SCOPE, "SHAREDkey", "SHAREDsecret", "99999999-01")
    # 유저 미등록 → 공유 fallback
    creds, source = store.resolve("7")
    assert source == "shared" and creds.app_key == "SHAREDkey"
    # 유저 등록 → 본인 키 우선
    store.upsert_encrypted("7", "MINEkey", "MINEsecret", "11111111-01")
    creds, source = store.resolve("7")
    assert source == "user" and creds.app_key == "MINEkey" and creds.account_no == "11111111"


def test_resolve_none_when_no_creds():
    db = _session()
    store = KisCredentialStore(db)
    assert store.resolve("7") is None
    assert store.resolve(None) is None


def test_resolve_anonymous_uses_shared():
    db = _session()
    store = KisCredentialStore(db)
    store.upsert_encrypted(SHARED_SCOPE, "SHAREDkey", "SHAREDsecret", "99999999-01")
    creds, source = store.resolve(None)  # 비로그인 → 공유
    assert source == "shared" and creds.app_key == "SHAREDkey"


def test_upsert_updates_same_row():
    db = _session()
    store = KisCredentialStore(db)
    store.upsert_encrypted("7", "k1", "s1", "10000000-01")
    store.upsert_encrypted("7", "k2", "s2", "20000000-01", env="demo")
    creds = store.get_decrypted("7")
    assert creds.app_key == "k2" and creds.env == "demo" and creds.account_no == "20000000"
    from auth.kis_models import KisCredentialRow
    assert db.query(KisCredentialRow).filter_by(scope_key="7").count() == 1  # 단일 행


def test_delete_falls_back_to_shared():
    db = _session()
    store = KisCredentialStore(db)
    store.upsert_encrypted(SHARED_SCOPE, "SHAREDkey", "SHAREDsecret", "99999999-01")
    store.upsert_encrypted("7", "MINEkey", "MINEsecret", "11111111-01")
    store.delete("7")
    assert store.get_decrypted("7") is None
    creds, source = store.resolve("7")  # 삭제 후 공유 복귀
    assert source == "shared"


def test_status_masks_never_plaintext():
    db = _session()
    store = KisCredentialStore(db)
    store.upsert_encrypted("7", "PSABCDEFGH12", "SECRETvalue", "12345678-01")
    st = store.status("7")
    assert st["registered"] is True and st["source"] == "user" and st["env"] == "real"
    assert st["app_key_masked"] == "PS••••12"  # 원문 미노출
    assert "SECRETvalue" not in str(st)  # 시크릿 절대 미노출


def test_status_shared_and_none():
    db = _session()
    store = KisCredentialStore(db)
    assert store.status("7") == {
        "registered": False, "source": "none", "app_key_masked": "", "account_masked": "", "env": "",
    }
    store.upsert_encrypted(SHARED_SCOPE, "SHAREDkey", "SHAREDsecret", "99999999-01")
    st = store.status("7")
    assert st["registered"] is False and st["source"] == "shared"
