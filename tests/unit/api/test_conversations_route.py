"""대화 라우트 — 목록/생성/메시지/삭제(인메모리 SQLite, 인증 오버라이드)·유저 격리·404."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import api.conversations as conv_route
from auth.deps import get_current_user
from chat.history_store import HistoryStore
from infra.db import Base, get_db, import_models


@pytest.fixture
def ctx():
    import_models()
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)

    def _override_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    def _app_for(uid):
        app = FastAPI()
        app.include_router(conv_route.router)
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uid)
        app.dependency_overrides[get_db] = _override_db
        return TestClient(app)

    return SimpleNamespace(client=_app_for(1), other=_app_for(2), Session=TestSession)


def test_create_and_list(ctx):
    r = ctx.client.post("/api/conversations", json={"title": "내 대화"})
    assert r.status_code == 200 and r.json()["title"] == "내 대화"
    conv_id = r.json()["id"]
    lst = ctx.client.get("/api/conversations").json()["conversations"]
    assert [c["id"] for c in lst] == [conv_id]


def test_rename_conversation(ctx):
    conv_id = ctx.client.post("/api/conversations", json={}).json()["id"]
    r = ctx.client.patch(f"/api/conversations/{conv_id}", json={"title": "삼성전자 분석"})
    assert r.status_code == 200 and r.json()["title"] == "삼성전자 분석"
    # 목록에도 반영.
    lst = ctx.client.get("/api/conversations").json()["conversations"]
    assert lst[0]["title"] == "삼성전자 분석"


def test_rename_not_owner_404(ctx):
    conv_id = ctx.client.post("/api/conversations", json={}).json()["id"]  # uid 1 소유
    r = ctx.other.patch(f"/api/conversations/{conv_id}", json={"title": "탈취"})  # uid 2
    assert r.status_code == 404
    assert ctx.client.get("/api/conversations").json()["conversations"][0]["title"] == "새 대화"


def test_rename_empty_title_422(ctx):
    conv_id = ctx.client.post("/api/conversations", json={}).json()["id"]
    assert ctx.client.patch(f"/api/conversations/{conv_id}", json={"title": ""}).status_code == 422
    assert ctx.client.patch(f"/api/conversations/{conv_id}", json={}).status_code == 422


def test_messages_empty_then_shape(ctx):
    conv_id = ctx.client.post("/api/conversations", json={}).json()["id"]
    r = ctx.client.get(f"/api/conversations/{conv_id}/messages")
    assert r.status_code == 200
    body = r.json()
    assert body["conversation"]["id"] == conv_id and body["messages"] == []


def test_user_isolation_and_404(ctx):
    conv_id = ctx.client.post("/api/conversations", json={"title": "A의 대화"}).json()["id"]
    # 다른 유저는 A 의 대화 목록에 없음.
    assert ctx.other.get("/api/conversations").json()["conversations"] == []
    # 다른 유저가 A 의 대화 메시지 조회 → 404.
    assert ctx.other.get(f"/api/conversations/{conv_id}/messages").status_code == 404
    # 다른 유저가 A 의 대화 삭제 → 404(소유권).
    assert ctx.other.delete(f"/api/conversations/{conv_id}").status_code == 404


def test_delete(ctx):
    conv_id = ctx.client.post("/api/conversations", json={}).json()["id"]
    assert ctx.client.delete(f"/api/conversations/{conv_id}").status_code == 200
    assert ctx.client.get(f"/api/conversations/{conv_id}/messages").status_code == 404


def test_requires_auth():
    app = FastAPI()
    app.include_router(conv_route.router)
    # 인증 오버라이드 없음 → 401.
    assert TestClient(app).get("/api/conversations").status_code == 401
