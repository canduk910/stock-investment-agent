"""POST /api/chat/report-context — 저장 요약을 세션 핀 컨텍스트로 세팅/해제/404(store mock)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.chat as chat_route
import chat.analyst_store as analyst_store
from chat.session import SESSIONS, get_session


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(chat_route.router)
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
    # 세션에 실제로 핀 컨텍스트가 걸렸는지(서버가 store 에서 조회해 세팅).
    ctx = get_session("s1").report_context
    assert ctx and "한화투자증권" in ctx and "실적 개선" in ctx


def test_clear_report_context_when_no_report_id(monkeypatch):
    SESSIONS.clear()
    get_session("s2").set_report_context("기존 컨텍스트")
    r = TestClient(_app()).post(
        "/api/chat/report-context", json={"session_id": "s2"}
    )
    assert r.status_code == 200 and r.json()["set"] is False
    assert get_session("s2").report_context is None  # 해제


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
