"""POST /api/chat/report-context — 저장 요약을 세션 핀 컨텍스트로 세팅/해제/404(store mock).

보안(추가): 이 엔드포인트는 **인증 필수** + 세션 owner 스코프다 — 토큰 없으면 401, 유저 B 가
유저 A 의 session_id 로 핀을 걸어도 자기(B) 세션에만 걸려 A 컨텍스트에 접근/오염할 수 없다(IDOR).
"""
from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.chat as chat_route
import chat.analyst_store as analyst_store
from auth.deps import get_current_user
from chat.session import SESSIONS, get_session
from infra.db import get_db


def _app(user_id="u1") -> FastAPI:
    """chat 라우터 앱. user_id 가 있으면 그 유저로 인증 오버라이드, None 이면 인증 미오버라이드
    (실 get_current_user 로 401 검증 — get_db 는 더미로 실 DB 미접촉)."""
    app = FastAPI()
    app.include_router(chat_route.router)
    if user_id is not None:
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)
    else:
        app.dependency_overrides[get_db] = lambda: SimpleNamespace()
    return app


class _Store:
    def __init__(self, entry):
        self._entry = entry

    def get(self, ticker, report_id):
        if self._entry and report_id == self._entry.get("report_id"):
            return self._entry
        return None


_ENTRY = {
    "report_id": "94082", "broker": "한화투자증권", "stock_name": "GS건설", "date": "26.07.10",
    "summary": {"증권사": "한화투자증권", "종목": "GS건설", "목표주가": "5만원",
                "투자의견": "매수", "요약": "실적 개선", "핵심요지": ["수주"],
                "리스크요인": ["원자재"], "면책고지": "자문 아님"},
}


def test_set_report_context_pins_summary(monkeypatch):
    SESSIONS.clear()
    monkeypatch.setattr(analyst_store, "default_store", lambda: _Store(_ENTRY))
    r = TestClient(_app()).post(
        "/api/chat/report-context",
        json={"session_id": "s1", "ticker": "006360", "report_id": "94082"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["set"] is True and body["broker"] == "한화투자증권"
    # 세션에 실제로 핀 컨텍스트가 걸렸는지(서버가 store 에서 조회해 세팅). owner=u1 스코프.
    ctx = get_session("s1", owner="u1").report_context
    assert ctx and "한화투자증권" in ctx and "실적 개선" in ctx


def test_clear_report_context_when_no_report_id(monkeypatch):
    SESSIONS.clear()
    get_session("s2", owner="u1").set_report_context("기존 컨텍스트")
    r = TestClient(_app()).post(
        "/api/chat/report-context", json={"session_id": "s2"}
    )
    assert r.status_code == 200 and r.json()["set"] is False
    assert get_session("s2", owner="u1").report_context is None  # 해제


def test_unknown_report_returns_404(monkeypatch):
    SESSIONS.clear()
    monkeypatch.setattr(analyst_store, "default_store", lambda: _Store(None))
    r = TestClient(_app()).post(
        "/api/chat/report-context",
        json={"session_id": "s3", "ticker": "006360", "report_id": "nope"},
    )
    assert r.status_code == 404


def test_bad_ticker_returns_400(monkeypatch):
    SESSIONS.clear()
    monkeypatch.setattr(analyst_store, "default_store", lambda: _Store(_ENTRY))
    r = TestClient(_app()).post(
        "/api/chat/report-context",
        json={"session_id": "s4", "ticker": "bad", "report_id": "94082"},
    )
    assert r.status_code == 400  # assert_valid_ticker


# ── 보안: 인증 필수 + 크로스유저(IDOR) 격리 ─────────────────────────────────────


def test_report_context_requires_auth():
    SESSIONS.clear()
    # 토큰 없이 호출 → 401(인증 미승격 상태였다면 200 이었다 — 이 테스트가 회귀 잠금).
    r = TestClient(_app(user_id=None)).post(
        "/api/chat/report-context",
        json={"session_id": "s1", "ticker": "006360", "report_id": "94082"},
    )
    assert r.status_code == 401


def test_pin_is_scoped_per_owner_not_leaked(monkeypatch):
    # 유저 A 가 session_id "42" 로 리포트 상담 컨텍스트를 핀 → 유저 B 가 같은 session_id 로 세션을
    # 열어도 A 의 컨텍스트가 안 보인다(owner 스코프). #1·#3 회귀 잠금.
    SESSIONS.clear()
    monkeypatch.setattr(analyst_store, "default_store", lambda: _Store(_ENTRY))
    ra = TestClient(_app(user_id="A")).post(
        "/api/chat/report-context",
        json={"session_id": "42", "ticker": "006360", "report_id": "94082"},
    )
    assert ra.status_code == 200 and ra.json()["set"] is True
    # A 세션엔 핀이 있고, 같은 session_id 의 B 세션엔 핀이 없다.
    assert get_session("42", owner="A").report_context is not None
    assert get_session("42", owner="B").report_context is None
