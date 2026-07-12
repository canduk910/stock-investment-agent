"""시황 요약 라우트 — fetch(수집·요약 mock)·list(store mock)·graceful."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.macro_outlook as mo


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(mo.router)
    return app


def test_fetch_returns_counts(monkeypatch):
    seen = {}

    def _fake(limit):
        seen["limit"] = limit
        return {"fetched": 2, "new": 1, "skipped": 1, "failed": 0}

    monkeypatch.setattr(mo.market_outlook_service, "fetch_and_summarize", _fake)
    r = TestClient(_app()).post("/api/macro/market-outlook/fetch?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert body["new"] == 1 and body["fetched"] == 2
    assert seen["limit"] == 10


def test_fetch_clamps_limit(monkeypatch):
    seen = {}

    def _fake(limit):
        seen["limit"] = limit
        return {"fetched": 0, "new": 0, "skipped": 0, "failed": 0}

    monkeypatch.setattr(mo.market_outlook_service, "fetch_and_summarize", _fake)
    TestClient(_app()).post("/api/macro/market-outlook/fetch?limit=999")
    assert seen["limit"] == 30


def test_fetch_graceful_on_error(monkeypatch):
    def _boom(limit):
        raise Exception("naver down")

    monkeypatch.setattr(mo.market_outlook_service, "fetch_and_summarize", _boom)
    r = TestClient(_app()).post("/api/macro/market-outlook/fetch")
    assert r.status_code == 200 and "error" in r.json()


def test_list_returns_reports(monkeypatch):
    class _Store:
        def list_reports(self):
            return [{"report_id": "36722", "broker": "KB증권", "summary": {}}]

    monkeypatch.setattr(mo, "default_store", lambda: _Store())
    r = TestClient(_app()).get("/api/macro/market-outlook")
    assert r.status_code == 200 and len(r.json()["reports"]) == 1
