"""POST /api/chat/market-outlook-context — 시황 요약을 세션 핀 컨텍스트로 세팅/해제/404(store mock).

애널리스트 report-context 와 동일 메커니즘(같은 세션 핀 슬롯)이되 시황은 시장 전체라 ticker 없음.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.chat as chat_route
import chat.market_outlook_store as outlook_store_mod
from chat.market_outlook import format_market_outlook_context
from chat.session import SESSIONS, get_session


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(chat_route.router)
    return app


class _Store:
    def __init__(self, entry):
        self._entry = entry

    def get(self, report_id):  # ticker 없음(시장 전체)
        if self._entry and report_id == self._entry.get("report_id"):
            return self._entry
        return None


_ENTRY = {
    "report_id": "77001", "broker": "미래에셋", "date": "26.07.20",
    "summary": {"증권사": "미래에셋", "제목": "7월 증시 전망", "시장전망": "중립",
                "요약": "박스권 예상", "세줄요약": ["a", "b", "c"], "핵심요지": ["금리"],
                "리스크요인": ["환율"], "면책고지": "자문 아님"},
}


def test_format_market_outlook_context_uses_outlook_fields():
    txt = format_market_outlook_context(_ENTRY)
    assert "미래에셋" in txt and "7월 증시 전망" in txt
    assert "시장전망" in txt and "중립" in txt
    assert "종목" not in txt  # 시장 전체 — 종목 라인 없음(애널리스트와 차이)
    assert "자문 아님" in txt  # 면책 포함


def test_set_market_outlook_context_pins(monkeypatch):
    SESSIONS.clear()
    monkeypatch.setattr(outlook_store_mod, "default_store", lambda: _Store(_ENTRY))
    r = TestClient(_app()).post(
        "/api/chat/market-outlook-context", json={"session_id": "m1", "report_id": "77001"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["set"] is True and body["broker"] == "미래에셋"
    ctx = get_session("m1").report_context  # 세션에 실제로 핀(서버가 store 조회해 세팅)
    assert ctx and "미래에셋" in ctx and "박스권" in ctx


def test_clear_market_outlook_context_when_no_report_id():
    SESSIONS.clear()
    get_session("m2").set_report_context("기존")
    r = TestClient(_app()).post("/api/chat/market-outlook-context", json={"session_id": "m2"})
    assert r.status_code == 200 and r.json()["set"] is False
    assert get_session("m2").report_context is None  # 해제


def test_unknown_market_outlook_returns_404(monkeypatch):
    SESSIONS.clear()
    monkeypatch.setattr(outlook_store_mod, "default_store", lambda: _Store(None))
    r = TestClient(_app()).post(
        "/api/chat/market-outlook-context", json={"session_id": "m3", "report_id": "nope"}
    )
    assert r.status_code == 404
