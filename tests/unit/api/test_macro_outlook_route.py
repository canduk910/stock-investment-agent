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


def test_fetch_stream_emits_progress_events(monkeypatch):
    def _fake(limit):
        assert limit == 5
        yield {"type": "stage", "stage": "list"}
        yield {"type": "found", "reports": [{"id": "36722", "broker": "KB증권", "title": "시황"}]}
        yield {"type": "progress", "id": "36722", "result": "new", "done": 1, "total": 1}
        yield {"type": "done", "fetched": 1, "new": 1, "skipped": 0, "failed": 0}

    monkeypatch.setattr(mo.market_outlook_service, "iter_fetch_and_summarize", _fake)
    r = TestClient(_app()).post("/api/macro/market-outlook/fetch/stream?limit=5")
    assert r.status_code == 200 and "text/event-stream" in r.headers["content-type"]
    import json
    types = [json.loads(l[6:])["type"] for l in r.text.splitlines() if l.startswith("data: ")]
    assert types == ["stage", "found", "progress", "done"]


def test_list_returns_reports(monkeypatch):
    class _Store:
        def list_reports(self):
            return [{"report_id": "36722", "broker": "KB증권", "summary": {}}]

    monkeypatch.setattr(mo, "default_store", lambda: _Store())
    r = TestClient(_app()).get("/api/macro/market-outlook")
    assert r.status_code == 200 and len(r.json()["reports"]) == 1


def test_combined_summary_route_returns_summary(monkeypatch):
    # POST /summary → market_outlook_combined.summarize_recent_outlooks 결과를 반환(graceful).
    monkeypatch.setattr(
        mo.market_outlook_combined,
        "summarize_recent_outlooks",
        lambda: {
            "validation_failed": False,
            "report_count": 5,
            "summary": {"시장전망분포": "중립 3·신중 2", "종합요약": ["a", "b"], "면책고지": "자문 아님"},
        },
    )
    r = TestClient(_app()).post("/api/macro/market-outlook/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["report_count"] == 5 and body["summary"]["시장전망분포"] == "중립 3·신중 2"


def test_combined_summary_route_graceful_on_error(monkeypatch):
    def _boom():
        raise RuntimeError("llm down")

    monkeypatch.setattr(mo.market_outlook_combined, "summarize_recent_outlooks", _boom)
    r = TestClient(_app()).post("/api/macro/market-outlook/summary")
    assert r.status_code == 200  # graceful_counts 폴백
    assert r.json()["validation_failed"] is True
