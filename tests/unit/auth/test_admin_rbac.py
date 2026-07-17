"""관리자 시드·게이트·/api/auth/me quota 노출(인메모리 SQLite)."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import api.auth as auth_route
from auth.models import User
from infra.db import Base, get_db, import_models


@pytest.fixture
def db_and_client():
    import_models()
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _override():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(auth_route.router)
    app.dependency_overrides[get_db] = _override
    return TestSession, TestClient(app)


def test_seed_admins_promotes_existing_user(db_and_client, monkeypatch):
    TestSession, client = db_and_client
    monkeypatch.setenv("ADMIN_EMAILS", "admin@test.com , other@x.com")
    # 가입한 유저만 승격(idempotent). 없는 이메일은 no-op.
    client.post("/api/auth/signup", json={"email": "admin@test.com", "password": "password123"})
    from auth.admin_seed import seed_admins

    promoted = seed_admins(session_factory=TestSession)
    assert promoted == 1  # admin@test.com 만(other 는 미가입)
    db = TestSession()
    u = db.scalar(select(User).where(User.email == "admin@test.com"))
    assert u.is_admin is True
    # 재실행 idempotent(이미 admin → 0 승격).
    assert seed_admins(session_factory=TestSession) == 0


def test_me_returns_is_admin_and_quota(db_and_client):
    TestSession, client = db_and_client
    r = client.post("/api/auth/signup", json={"email": "u@b.com", "password": "password123"})
    token = r.json()["token"]
    # 신규 유저: is_admin False, 오늘 사용 0, 잔량 = 기본 한도.
    user = r.json()["user"]
    assert user["is_admin"] is False
    assert user["used_today"] == 0 and user["daily_limit"] == 20 and user["remaining"] == 20
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["is_admin"] is False and me.json()["remaining"] == 20
