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


# ── 네이버 애널리스트 리포트 수집·조회 ──
def test_fetch_returns_counts(monkeypatch):
    calls = {}

    def _fake(limit):
        calls["limit"] = limit
        return {"fetched": 3, "new": 2, "skipped": 1, "failed": 0}

    monkeypatch.setattr(reports.analyst_service, "fetch_and_summarize", _fake)
    r = TestClient(_app()).post("/api/reports/fetch?limit=5")
    assert r.status_code == 200
    body = r.json()
    assert body["new"] == 2 and body["fetched"] == 3
    assert calls["limit"] == 5


def test_fetch_clamps_limit(monkeypatch):
    seen = {}

    def _fake(limit):
        seen["limit"] = limit
        return {"fetched": 0, "new": 0, "skipped": 0, "failed": 0}

    monkeypatch.setattr(reports.analyst_service, "fetch_and_summarize", _fake)
    TestClient(_app()).post("/api/reports/fetch?limit=999")
    assert seen["limit"] == 50  # 상한 클램프


def test_fetch_graceful_on_error(monkeypatch):
    def _boom(limit):
        raise Exception("naver down")

    monkeypatch.setattr(reports.analyst_service, "fetch_and_summarize", _boom)
    r = TestClient(_app()).post("/api/reports/fetch")
    assert r.status_code == 200 and "error" in r.json()  # graceful


# ── 종목별 수집(itemCode 필터) — POST /api/detail/{ticker}/analyst-reports/fetch ──
def test_fetch_stock_reports_passes_ticker(monkeypatch):
    calls = {}

    def _fake(ticker, limit):
        calls["ticker"] = ticker
        calls["limit"] = limit
        return {"fetched": 2, "new": 2, "skipped": 0, "failed": 0}

    monkeypatch.setattr(reports.analyst_service, "fetch_and_summarize_for_ticker", _fake)
    r = TestClient(_app()).post("/api/detail/006360/analyst-reports/fetch?limit=5")
    assert r.status_code == 200
    assert r.json()["new"] == 2
    assert calls == {"ticker": "006360", "limit": 5}  # 그 종목·limit 로 위임


def test_fetch_stock_reports_clamps_limit(monkeypatch):
    seen = {}

    def _fake(ticker, limit):
        seen["limit"] = limit
        return {"fetched": 0, "new": 0, "skipped": 0, "failed": 0}

    monkeypatch.setattr(reports.analyst_service, "fetch_and_summarize_for_ticker", _fake)
    TestClient(_app()).post("/api/detail/006360/analyst-reports/fetch?limit=999")
    assert seen["limit"] == 30  # 종목별 상한 클램프


def test_fetch_stock_reports_rejects_bad_ticker():
    r = TestClient(_app()).post("/api/detail/notaticker/analyst-reports/fetch")
    assert r.status_code == 400  # assert_valid_ticker


# ── SSE 진행 스트림 ──
def _sse_events(body: str):
    import json
    return [json.loads(l[6:]) for l in body.splitlines() if l.startswith("data: ")]


def test_fetch_stream_emits_progress_events(monkeypatch):
    def _fake(ticker, limit):
        assert ticker == "006360" and limit == 5
        yield {"type": "stage", "stage": "list"}
        yield {"type": "found", "reports": [{"id": "1", "broker": "한화", "title": "t"}]}
        yield {"type": "progress", "id": "1", "result": "new", "done": 1, "total": 1}
        yield {"type": "done", "fetched": 1, "new": 1, "skipped": 0, "failed": 0}

    monkeypatch.setattr(reports.analyst_service, "iter_fetch_and_summarize_for_ticker", _fake)
    r = TestClient(_app()).post("/api/detail/006360/analyst-reports/fetch/stream?limit=5")
    assert r.status_code == 200 and "text/event-stream" in r.headers["content-type"]
    types = [e["type"] for e in _sse_events(r.text)]
    assert types == ["stage", "found", "progress", "done"]


def test_fetch_stream_generator_error_is_graceful(monkeypatch):
    def _boom(ticker, limit):
        yield {"type": "stage", "stage": "list"}
        raise RuntimeError("naver down")

    monkeypatch.setattr(reports.analyst_service, "iter_fetch_and_summarize_for_ticker", _boom)
    r = TestClient(_app()).post("/api/detail/006360/analyst-reports/fetch/stream")
    assert r.status_code == 200  # 스트림 시작됨(200) → 중간 실패는 error 프레임
    events = _sse_events(r.text)
    assert events[-1]["type"] == "error" and "naver" in events[-1]["message"]


def test_fetch_stream_rejects_bad_ticker():
    r = TestClient(_app()).post("/api/detail/notaticker/analyst-reports/fetch/stream")
    assert r.status_code == 400  # 스트림 전 assert_valid_ticker


def test_fetch_stock_reports_graceful_on_error(monkeypatch):
    def _boom(ticker, limit):
        raise Exception("naver down")

    monkeypatch.setattr(reports.analyst_service, "fetch_and_summarize_for_ticker", _boom)
    r = TestClient(_app()).post("/api/detail/006360/analyst-reports/fetch")
    assert r.status_code == 200 and "error" in r.json()  # graceful


def test_analyst_reports_lists_for_ticker(monkeypatch):
    class _Store:
        def list_reports(self, ticker):
            return [{"report_id": "1", "broker": "한화투자증권", "summary": {}}]

    monkeypatch.setattr(reports, "default_store", lambda: _Store())
    r = TestClient(_app()).get("/api/detail/006360/analyst-reports")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "006360" and len(body["reports"]) == 1


def test_analyst_reports_rejects_bad_ticker():
    r = TestClient(_app()).get("/api/detail/notaticker/analyst-reports")
    assert r.status_code == 400  # assert_valid_ticker


# ── 최근 3개 종합 10줄요약(항목5) — POST /api/detail/{ticker}/analyst-reports/summary ──
def test_analyst_summary_happy_path(monkeypatch):
    calls = {}

    def _fake(ticker):
        calls["ticker"] = ticker
        return {
            "summary": {"종목": "GS건설", "의견분포": "매수 2·중립 1", "목표주가범위": "5만원~5.5만원",
                        "종합요약": ["실적 개선", "수주 회복"], "면책고지": "리포트 종합·자문 아님."},
            "validation_failed": False, "report_count": 2,
        }

    monkeypatch.setattr(reports.analyst_combined, "summarize_recent_reports", _fake)
    r = TestClient(_app()).post("/api/detail/006360/analyst-reports/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "006360" and calls["ticker"] == "006360"
    assert body["validation_failed"] is False and body["report_count"] == 2
    assert body["summary"]["의견분포"] == "매수 2·중립 1"


def test_analyst_summary_no_reports_graceful(monkeypatch):
    # 저장 리포트 0개 → 항상 200 + validation_failed(안내).
    monkeypatch.setattr(
        reports.analyst_combined, "summarize_recent_reports",
        lambda ticker: {"summary": None, "validation_failed": True, "report_count": 0, "message": "리포트 없음"},
    )
    r = TestClient(_app()).post("/api/detail/006360/analyst-reports/summary")
    assert r.status_code == 200
    assert r.json()["validation_failed"] is True and r.json()["report_count"] == 0


def test_analyst_summary_graceful_on_error(monkeypatch):
    def _boom(ticker):
        raise Exception("openai down")

    monkeypatch.setattr(reports.analyst_combined, "summarize_recent_reports", _boom)
    r = TestClient(_app()).post("/api/detail/006360/analyst-reports/summary")
    assert r.status_code == 200 and r.json()["validation_failed"] is True  # 크래시 아님


def test_analyst_summary_rejects_bad_ticker():
    r = TestClient(_app()).post("/api/detail/notaticker/analyst-reports/summary")
    assert r.status_code == 400  # assert_valid_ticker
