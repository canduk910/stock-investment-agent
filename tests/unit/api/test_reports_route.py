"""증권사 리포트 RAG 라우트 테스트 — reindex/status(store facade mock).

POST /api/reports/reindex : 인덱스 재구축 요약. 실패는 graceful(항상 200 + error).
GET  /api/reports/status  : 인덱스 요약. api.main 은 편집하지 않고 로컬 앱에 라우터만 include.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.reports as reports


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(reports.router)
    return app


def test_reindex_returns_summary(monkeypatch):
    monkeypatch.setattr(
        reports.store, "reindex",
        lambda: {"reports": 2, "chunks": 10, "sources": ["a.pdf", "b.pdf"]},
    )
    r = TestClient(_app()).post("/api/reports/reindex")
    assert r.status_code == 200
    body = r.json()
    assert body["reports"] == 2 and body["chunks"] == 10


def test_reindex_graceful_on_error(monkeypatch):
    def _boom():
        raise Exception("openai down")

    monkeypatch.setattr(reports.store, "reindex", _boom)
    r = TestClient(_app()).post("/api/reports/reindex")
    assert r.status_code == 200  # 크래시 아니라 graceful
    assert "error" in r.json()


def test_status(monkeypatch):
    monkeypatch.setattr(
        reports.store, "status", lambda: {"reports": 1, "chunks": 5, "sources": ["a.pdf"]}
    )
    r = TestClient(_app()).get("/api/reports/status")
    assert r.status_code == 200 and r.json()["chunks"] == 5
