"""관리자 라우터 계약 — 유저 목록·한도 제어·이용 통계·삭제(인메모리 SQLite).

get_admin_user 게이트(비관리자 403), PATCH 부분갱신, reset-usage, 삭제 시 스코프 데이터 정리,
자기 자신 관리자해제/삭제 방지. 실 DB/키 없이 라우트 계약만 검증.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import api.admin as admin_route
import api.auth as auth_route
from auth.deps import get_current_user
from auth.models import User
from auth.security import hash_password
from auth.usage import today_kst
from infra.db import Base, get_db, import_models


@pytest.fixture
def ctx():
    import_models()
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(auth_route.router)
    app.include_router(admin_route.router)
    app.dependency_overrides[get_db] = _get_db

    def as_user(u: User):
        app.dependency_overrides[get_current_user] = lambda: u

    return SimpleNamespace(client=TestClient(app), Session=Session, as_user=as_user)


def _make_user(Session, email, **kw) -> User:
    db = Session()
    u = User(email=email, password_hash=hash_password("password123"), **kw)
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u


def test_non_admin_forbidden(ctx):
    member = _make_user(ctx.Session, "u@a.com", is_admin=False)
    ctx.as_user(member)
    assert ctx.client.get("/api/admin/users").status_code == 403
    assert ctx.client.patch(f"/api/admin/users/{member.id}", json={"daily_limit": 5}).status_code == 403


def test_admin_lists_users_with_stats_no_hash(ctx):
    admin = _make_user(ctx.Session, "admin@a.com", is_admin=True)
    _make_user(ctx.Session, "member@a.com", used_today=3, usage_date=today_kst(), total_questions=9)
    ctx.as_user(admin)
    r = ctx.client.get("/api/admin/users")
    assert r.status_code == 200
    users = r.json()["users"]
    assert {u["email"] for u in users} == {"admin@a.com", "member@a.com"}
    m = next(u for u in users if u["email"] == "member@a.com")
    assert m["used_today"] == 3 and m["remaining"] == 17 and m["total_questions"] == 9
    assert "password_hash" not in m and "password" not in m  # 해시·비번 미노출
    a = next(u for u in users if u["email"] == "admin@a.com")
    assert a["is_admin"] is True and a["remaining"] is None  # 관리자 무제한


def test_patch_updates_limit_and_admin(ctx):
    admin = _make_user(ctx.Session, "admin@a.com", is_admin=True)
    m = _make_user(ctx.Session, "m@a.com", daily_limit=20)
    ctx.as_user(admin)
    r = ctx.client.patch(f"/api/admin/users/{m.id}", json={"daily_limit": 5, "is_admin": True})
    assert r.status_code == 200 and r.json()["daily_limit"] == 5 and r.json()["is_admin"] is True
    db = ctx.Session()
    got = db.get(User, m.id)
    assert got.daily_limit == 5 and got.is_admin is True
    db.close()


def test_patch_partial_only_sent_fields(ctx):
    admin = _make_user(ctx.Session, "admin@a.com", is_admin=True)
    m = _make_user(ctx.Session, "m@a.com", is_admin=True, daily_limit=20)
    ctx.as_user(admin)
    # daily_limit 만 보냄 → is_admin 은 불변(부분 갱신)
    r = ctx.client.patch(f"/api/admin/users/{m.id}", json={"daily_limit": 3})
    assert r.status_code == 200 and r.json()["daily_limit"] == 3 and r.json()["is_admin"] is True


def test_patch_rejects_negative_limit(ctx):
    admin = _make_user(ctx.Session, "admin@a.com", is_admin=True)
    m = _make_user(ctx.Session, "m@a.com")
    ctx.as_user(admin)
    assert ctx.client.patch(f"/api/admin/users/{m.id}", json={"daily_limit": -1}).status_code == 422


def test_patch_missing_user_404(ctx):
    admin = _make_user(ctx.Session, "admin@a.com", is_admin=True)
    ctx.as_user(admin)
    assert ctx.client.patch("/api/admin/users/9999", json={"daily_limit": 5}).status_code == 404


def test_self_demote_blocked(ctx):
    admin = _make_user(ctx.Session, "admin@a.com", is_admin=True)
    ctx.as_user(admin)
    r = ctx.client.patch(f"/api/admin/users/{admin.id}", json={"is_admin": False})
    assert r.status_code == 400  # 락아웃 방지


def test_reset_usage_zeroes_today_keeps_total(ctx):
    admin = _make_user(ctx.Session, "admin@a.com", is_admin=True)
    m = _make_user(ctx.Session, "m@a.com", used_today=20, usage_date=today_kst(), total_questions=50)
    ctx.as_user(admin)
    r = ctx.client.post(f"/api/admin/users/{m.id}/reset-usage")
    assert r.status_code == 200
    body = r.json()
    assert body["used_today"] == 0 and body["remaining"] == body["daily_limit"]
    assert body["total_questions"] == 50  # 누적 통계는 보존


def test_delete_self_blocked(ctx):
    admin = _make_user(ctx.Session, "admin@a.com", is_admin=True)
    ctx.as_user(admin)
    assert ctx.client.delete(f"/api/admin/users/{admin.id}").status_code == 400


def test_delete_removes_user_and_scoped_data(ctx):
    from auth.kis_models import KisCredentialRow
    from chat.history_models import ChatMessage, Conversation
    from watchlist.db_models import WatchlistItemRow

    admin = _make_user(ctx.Session, "admin@a.com", is_admin=True)
    m = _make_user(ctx.Session, "m@a.com")
    scope = str(m.id)

    db = ctx.Session()
    db.add(WatchlistItemRow(user_id=scope, ticker="005930", stock_name="삼성전자", added_at="2026-01-01T00:00:00"))
    conv = Conversation(user_id=scope, title="t")
    db.add(conv)
    db.flush()
    conv_id = conv.id
    db.add(ChatMessage(conversation_id=conv_id, role="user", content="hi"))
    db.add(KisCredentialRow(scope_key=scope, app_key_enc="x", app_secret_enc="y"))
    db.commit()
    db.close()

    ctx.as_user(admin)
    r = ctx.client.delete(f"/api/admin/users/{m.id}")
    assert r.status_code == 200 and r.json()["deleted"] == m.id

    db = ctx.Session()
    assert db.get(User, m.id) is None
    assert db.query(WatchlistItemRow).filter(WatchlistItemRow.user_id == scope).count() == 0
    assert db.query(Conversation).filter(Conversation.user_id == scope).count() == 0
    assert db.query(ChatMessage).filter(ChatMessage.conversation_id == conv_id).count() == 0
    assert db.query(KisCredentialRow).filter(KisCredentialRow.scope_key == scope).count() == 0
    db.close()
