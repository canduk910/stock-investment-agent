"""사이트 통계 — 방문 카운터(누적+오늘 리셋) + 가입자수 집계 + 라우트 계약.

방문은 누적 +1 / 오늘은 KST 날짜 경계에서 리셋. get 은 회원 총수도 센다. PII 없음·항상 200.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import api.stats as stats_route
from auth.models import User
from auth.security import hash_password
from infra import site_stats
from infra.db import Base, get_db, import_models


@pytest.fixture
def env():
    import_models()
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
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
    app.include_router(stats_route.router)
    app.dependency_overrides[get_db] = _get_db
    return SimpleNamespace(client=TestClient(app), Session=Session)


def test_record_visit_increments_total_and_today(env, monkeypatch):
    monkeypatch.setattr(site_stats, "_today_kst", lambda: "2026-07-20")
    db = env.Session()
    assert site_stats.record_visit(db) == {"total_visits": 1, "today_visits": 1}
    assert site_stats.record_visit(db) == {"total_visits": 2, "today_visits": 2}


def test_today_resets_on_date_change_total_persists(env, monkeypatch):
    db = env.Session()
    monkeypatch.setattr(site_stats, "_today_kst", lambda: "2026-07-20")
    site_stats.record_visit(db)
    site_stats.record_visit(db)  # 오늘 2
    monkeypatch.setattr(site_stats, "_today_kst", lambda: "2026-07-21")  # 다음날 경계
    assert site_stats.record_visit(db) == {"total_visits": 3, "today_visits": 1}  # 누적 유지·오늘 리셋


def test_get_site_stats_counts_members_and_visits(env, monkeypatch):
    monkeypatch.setattr(site_stats, "_today_kst", lambda: "2026-07-20")
    db = env.Session()
    db.add(User(email="a@x.com", password_hash=hash_password("pw12345678")))
    db.add(User(email="b@x.com", password_hash=hash_password("pw12345678")))
    db.commit()
    site_stats.record_visit(db)
    s = site_stats.get_site_stats(db)
    assert s == {"member_count": 2, "total_visits": 1, "today_visits": 1}


def test_get_stats_today_zero_when_stale(env, monkeypatch):
    db = env.Session()
    monkeypatch.setattr(site_stats, "_today_kst", lambda: "2026-07-20")
    site_stats.record_visit(db)  # today_date=20
    monkeypatch.setattr(site_stats, "_today_kst", lambda: "2026-07-21")  # 조회 시 다음날
    s = site_stats.get_site_stats(db)
    assert s["total_visits"] == 1 and s["today_visits"] == 0  # 오늘 0(리셋 전 조회 방어)


def test_routes_visit_then_stats(env, monkeypatch):
    monkeypatch.setattr(site_stats, "_today_kst", lambda: "2026-07-20")
    c = env.client
    assert c.post("/api/visit").json()["total_visits"] == 1
    body = c.get("/api/stats").json()
    assert body == {"member_count": 0, "total_visits": 1, "today_visits": 1}
