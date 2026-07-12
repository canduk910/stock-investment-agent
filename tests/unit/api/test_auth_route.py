"""인증 라우트 — signup/login/me(인메모리 SQLite, get_db 오버라이드). 비번 해시 미노출."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import api.auth as auth_route
from infra.db import Base, get_db, import_models


@pytest.fixture
def client():
    import_models()  # User 테이블을 Base.metadata 에 등록
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
    return TestClient(app)


def _signup(client, email="a@b.com", pw="password123"):
    return client.post("/api/auth/signup", json={"email": email, "password": pw})


def test_signup_returns_token_and_user_no_hash(client):
    r = _signup(client)
    assert r.status_code == 200
    body = r.json()
    assert body["token"] and body["user"]["email"] == "a@b.com"
    assert "password" not in str(body) and "hash" not in str(body)  # 해시 미노출


def test_signup_duplicate_email_409(client):
    _signup(client)
    r = _signup(client)
    assert r.status_code == 409


def test_signup_weak_password_422(client):
    r = client.post("/api/auth/signup", json={"email": "x@y.com", "password": "short"})
    assert r.status_code == 422  # min_length=8


def test_login_success_and_wrong_password(client):
    _signup(client, pw="mypassword1")
    ok = client.post("/api/auth/login", json={"email": "a@b.com", "password": "mypassword1"})
    assert ok.status_code == 200 and ok.json()["token"]
    bad = client.post("/api/auth/login", json={"email": "a@b.com", "password": "wrongpass1"})
    assert bad.status_code == 401


def test_login_unknown_email_401(client):
    r = client.post("/api/auth/login", json={"email": "nope@x.com", "password": "whatever1"})
    assert r.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer bad"}).status_code == 401


def test_me_returns_current_user(client):
    token = _signup(client).json()["token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["email"] == "a@b.com"


def test_email_normalized_lowercase(client):
    _signup(client, email="Mixed@Case.COM")
    # 대문자로 가입해도 소문자로 로그인 가능(정규화).
    r = client.post("/api/auth/login", json={"email": "mixed@case.com", "password": "password123"})
    assert r.status_code == 200
