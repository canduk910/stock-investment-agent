"""api.main W10 라우터 wiring + CORS 회귀 스모크(IMP-18).

라우트 유닛은 로컬 FastAPI 앱으로 검증하므로 api.main 의 include_router(watchlist·report)나
CORS allow_methods 의 DELETE/PATCH 가 빠져도 전부 초록이다(실증됨). 여기서 통합 앱(api.main.app)
으로 (1) 라우터 mount(404 아님), (2) DELETE/PATCH 프리플라이트 허용을 고정한다.
경계(store·KIS·judgement)는 mock — 실 API 미호출.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api.main as main
import api.report as report_mod
import api.watchlist as wl
from watchlist.store import InMemoryWatchlistStore


class _EmptyHistoryStore:
    def list_history(self, ticker):
        return []


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(wl, "_get_store", lambda: InMemoryWatchlistStore())
    monkeypatch.setattr(wl, "_build_kis_client", lambda: object())
    monkeypatch.setattr(wl, "_build_judgement", lambda: None)  # 국면 degraded(시세 없어도 200)
    monkeypatch.setattr(report_mod, "_get_store", lambda: _EmptyHistoryStore())
    return TestClient(main.app)


def test_watchlist_router_mounted(client):
    # include_router(watchlist) 가 빠지면 404 → wiring 회귀를 잡는다.
    r = client.get("/api/watchlist")
    assert r.status_code == 200
    assert set(r.json()) >= {"items", "regime", "partial_failure", "sort_by"}


def test_report_history_router_mounted(client):
    r = client.get("/api/detail/005930/report/history")
    assert r.status_code == 200
    assert r.json()["history"] == []


@pytest.mark.parametrize("method", ["DELETE", "PATCH"])
def test_cors_preflight_allows_delete_and_patch(client, method):
    # CORS allow_methods 에서 DELETE/PATCH 가 빠지면 프리플라이트 allow-methods 에 안 실린다.
    r = client.options(
        "/api/watchlist/005930",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": method,
        },
    )
    assert r.status_code == 200
    assert method in r.headers.get("access-control-allow-methods", "")
