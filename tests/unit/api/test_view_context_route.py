"""POST /api/chat/context — 현재 화면 스냅샷 세션 핀/해제(build_view_context mock)·세션 격리.

보안(추가): 이 엔드포인트는 옵션 인증 → **인증 필수** 로 승격 + 세션 owner 스코프(토큰 없으면
401·유저 B 가 A 의 session_id 로 자기 스냅샷을 걸어도 A 세션엔 닿지 않음 — IDOR 차단).
"""
from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.chat as chat_route
import chat.view_context as vc
from auth.deps import get_current_user
from chat.session import SESSIONS, get_session
from infra.db import get_db


def _app(user_id="u1") -> FastAPI:
    app = FastAPI()
    app.include_router(chat_route.router)
    if user_id is not None:
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)
        app.dependency_overrides[get_db] = lambda: SimpleNamespace()  # build_view_context 는 mock
    else:
        app.dependency_overrides[get_db] = lambda: SimpleNamespace()
    return app


def test_data_kind_pins_snapshot(monkeypatch):
    SESSIONS.clear()
    monkeypatch.setattr(vc, "build_view_context", lambda kind, args, **kw: "기준시각: T\n순자산 1,900만원")
    r = TestClient(_app()).post(
        "/api/chat/context", json={"session_id": "s1", "kind": "balance", "args": {}}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["set"] is True and body["kind"] == "balance"
    ctx = get_session("s1", owner="u1").view_context
    assert ctx and "순자산 1,900만원" in ctx


def test_stock_kind_forwards_args(monkeypatch):
    SESSIONS.clear()
    seen = {}

    def _fake(kind, args, **kw):
        seen["kind"] = kind
        seen["args"] = args
        return "기준시각: T\n종목"

    monkeypatch.setattr(vc, "build_view_context", _fake)
    TestClient(_app()).post(
        "/api/chat/context",
        json={"session_id": "s2", "kind": "stock_report", "args": {"ticker": "005930"}},
    )
    assert seen["kind"] == "stock_report" and seen["args"] == {"ticker": "005930"}


def test_none_result_clears(monkeypatch):
    SESSIONS.clear()
    get_session("s3", owner="u1").set_view_context("이전 스냅샷")
    monkeypatch.setattr(vc, "build_view_context", lambda kind, args, **kw: None)  # 조회 불가
    r = TestClient(_app()).post(
        "/api/chat/context", json={"session_id": "s3", "kind": "stock_report", "args": {"ticker": "bad"}}
    )
    assert r.status_code == 200 and r.json()["set"] is False
    assert get_session("s3", owner="u1").view_context is None  # 해제


def test_non_data_kind_clears(monkeypatch):
    SESSIONS.clear()
    get_session("s4", owner="u1").set_view_context("이전 스냅샷")
    # macro_dashboard 는 비데이터 → build_view_context 호출 없이 해제.
    r = TestClient(_app()).post(
        "/api/chat/context", json={"session_id": "s4", "kind": "macro_dashboard", "args": {}}
    )
    assert r.status_code == 200 and r.json()["set"] is False
    assert get_session("s4", owner="u1").view_context is None


def test_missing_kind_clears():
    SESSIONS.clear()
    get_session("s5", owner="u1").set_view_context("이전 스냅샷")
    r = TestClient(_app()).post("/api/chat/context", json={"session_id": "s5"})
    assert r.status_code == 200 and r.json()["set"] is False
    assert get_session("s5", owner="u1").view_context is None


def test_session_isolation(monkeypatch):
    SESSIONS.clear()
    monkeypatch.setattr(vc, "build_view_context", lambda kind, args, **kw: "기준시각: T\n잔고")
    TestClient(_app()).post(
        "/api/chat/context", json={"session_id": "a", "kind": "balance", "args": {}}
    )
    assert get_session("a", owner="u1").view_context is not None
    assert get_session("b", owner="u1").view_context is None  # 다른 세션은 격리


# ── 보안: 인증 필수 + 크로스유저(IDOR) 격리 ─────────────────────────────────────


def test_view_context_requires_auth():
    SESSIONS.clear()
    r = TestClient(_app(user_id=None)).post(
        "/api/chat/context", json={"session_id": "s1", "kind": "balance", "args": {}}
    )
    assert r.status_code == 401


def test_view_pin_scoped_per_owner(monkeypatch):
    # 유저 A 가 화면 스냅샷을 핀 → 같은 session_id 의 유저 B 세션엔 안 실린다(owner 스코프).
    SESSIONS.clear()
    monkeypatch.setattr(vc, "build_view_context", lambda kind, args, **kw: "기준시각: T\nA 잔고")
    TestClient(_app(user_id="A")).post(
        "/api/chat/context", json={"session_id": "42", "kind": "balance", "args": {}}
    )
    assert get_session("42", owner="A").view_context is not None
    assert get_session("42", owner="B").view_context is None
