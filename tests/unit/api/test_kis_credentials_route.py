"""KIS 자격증명 라우트 — 검증후저장·마스킹조회(원문 미노출)·삭제·401·검증실패 400."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import api.kis_credentials as mod
from auth.deps import get_current_user
from infra.db import Base, get_db, import_models


class _User:
    id = 7
    email = "a@example.com"


def _session_factory():
    import_models()
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _get_db_override(SessionLocal):
    def _get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    return _get_db


def _make_app(monkeypatch, *, valid=True, with_user=True) -> FastAPI:
    SessionLocal = _session_factory()

    def _rt(config, clock=None):  # request_token mock
        if not valid:
            raise RuntimeError("EGW00133 유효하지 않은 appkey")
        return {"access_token": "T", "token_type": "Bearer", "expires_at": 1}

    monkeypatch.setattr(mod.kis_auth, "request_token", _rt)

    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_db] = _get_db_override(SessionLocal)
    if with_user:
        app.dependency_overrides[get_current_user] = lambda: _User()
    return app


def test_post_validates_then_stores_masked(monkeypatch):
    c = TestClient(_make_app(monkeypatch, valid=True))
    r = c.post(
        "/api/me/kis-credentials",
        json={"app_key": "PSABCDEFGH12", "app_secret": "SECRETval", "account_no": "12345678-01"},
    )
    assert r.status_code == 200
    st = r.json()["status"]
    assert st["registered"] is True and st["source"] == "user"
    assert st["app_key_masked"] == "PS••••12" and st["account_masked"] == "12••••78"
    g = c.get("/api/me/kis-credentials").json()  # GET 도 마스킹만
    assert g["registered"] is True
    assert "PSABCDEFGH12" not in str(g) and "SECRETval" not in str(g)  # 원문 미노출


def test_post_invalid_key_400_not_stored(monkeypatch):
    c = TestClient(_make_app(monkeypatch, valid=False))
    r = c.post("/api/me/kis-credentials", json={"app_key": "BAD", "app_secret": "S"})
    assert r.status_code == 400
    assert "BAD" not in r.json()["detail"]  # 키 값 미노출
    assert c.get("/api/me/kis-credentials").json()["registered"] is False  # 저장 안 됨


def test_delete_removes_falls_back(monkeypatch):
    c = TestClient(_make_app(monkeypatch, valid=True))
    c.post("/api/me/kis-credentials", json={"app_key": "K", "app_secret": "S"})
    d = c.delete("/api/me/kis-credentials")
    assert d.status_code == 200 and d.json()["status"]["registered"] is False


def test_requires_auth(monkeypatch):
    c = TestClient(_make_app(monkeypatch, with_user=False))  # get_current_user 미오버라이드
    assert c.get("/api/me/kis-credentials").status_code == 401
    assert c.post(
        "/api/me/kis-credentials", json={"app_key": "K", "app_secret": "S"}
    ).status_code == 401
    assert c.delete("/api/me/kis-credentials").status_code == 401
