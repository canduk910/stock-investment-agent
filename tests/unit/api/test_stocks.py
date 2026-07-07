"""종목 검색 라우트 계약 테스트 — GET /api/stocks/search.

마스터 로더(_get_master)를 mock 해 네트워크 없이 검색·폴백을 검증한다.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

import api.main as main
import api.stocks as stocks

_MASTER = [
    {"ticker": "005930", "name": "삼성전자", "market": "KOSPI"},
    {"ticker": "000660", "name": "SK하이닉스", "market": "KOSPI"},
    {"ticker": "247540", "name": "에코프로비엠", "market": "KOSDAQ"},
]


def _client(monkeypatch):
    monkeypatch.setattr(stocks, "_get_master", lambda: _MASTER)
    return TestClient(main.app)


def test_search_by_name(monkeypatch):
    resp = _client(monkeypatch).get("/api/stocks/search", params={"q": "삼성"})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert [r["ticker"] for r in results] == ["005930"]
    assert results[0]["market"] == "KOSPI"


def test_search_by_ticker(monkeypatch):
    resp = _client(monkeypatch).get("/api/stocks/search", params={"q": "000660"})
    assert resp.json()["results"][0]["name"] == "SK하이닉스"


def test_search_limit_capped(monkeypatch):
    resp = _client(monkeypatch).get("/api/stocks/search", params={"q": "에코", "limit": 999})
    assert resp.status_code == 200  # limit 30 으로 캡, 에러 없음


def test_search_empty_query(monkeypatch):
    resp = _client(monkeypatch).get("/api/stocks/search", params={"q": ""})
    assert resp.json()["results"] == []


def test_master_load_failure_is_graceful(monkeypatch):
    def _boom():
        raise RuntimeError("마스터 다운로드 실패")

    monkeypatch.setattr(stocks, "_get_master", _boom)
    resp = TestClient(main.app).get("/api/stocks/search", params={"q": "삼성"})
    assert resp.status_code == 200  # 죽지 않음
    body = resp.json()
    assert body["results"] == [] and "error" in body
