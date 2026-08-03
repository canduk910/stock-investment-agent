"""대순환 후보 스크리너 라우트 계약 테스트 — GET /api/screener (TDD Red→Green).

두 경로: **scope=cached(기본)** = DB 최신 스캔 결과(전체 유니버스) / **scope=live** = 시총상위 라이브.
서비스(screen_grand_cycle)·store·KIS 클라이언트 해석(_resolve_client)을 경계 mock 으로 대체하고,
market 화이트리스트 폴백·size clamp·DB 비면 live 폴백·항상 200 graceful 을 검증한다.

안전·정책: 조회 전용(GET only, 주문 없음) · KIS 실패는 항상 200 + partial_failure.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.screener as screener


def _no_db():
    yield None  # _resolve_client 를 patch 했으므로 실제 DB 불요


def _app():
    from infra.db import get_db

    app = FastAPI()
    app.include_router(screener.router)
    app.dependency_overrides[get_db] = _no_db
    return TestClient(app)


class _FakeStore:
    def __init__(self, latest=None, rows=None):
        self._latest = latest
        self._rows = rows or []

    def latest_as_of(self):
        return self._latest

    def list_results(self, as_of_date=None, market=None, stage=None):
        rows = self._rows
        if market is not None:
            rows = [r for r in rows if r.get("market") == market]
        if stage is not None:
            rows = [r for r in rows if r.get("stage") == stage]
        return list(rows)


def _stub(monkeypatch, *, service=None, store=None):
    monkeypatch.setattr(screener, "_resolve_client", lambda user, db: object())
    if service is not None:
        monkeypatch.setattr(screener, "screen_grand_cycle", service)
    if store is not None:
        monkeypatch.setattr(screener, "_get_store", lambda: store)


def _cand(ticker, name, market="KOSPI", stage=1):
    return {"ticker": ticker, "name": name, "market": market, "stage": stage,
            "stage_name": "안정 상승기", "arrangement": "단 > 중 > 장",
            "band_width_pct": 5.0, "band_direction": "확대", "bars_in_stage": 3}


# ── scope=cached (기본) ───────────────────────────────────────────────────────

def test_cached_default_returns_db_results(monkeypatch):
    store = _FakeStore(latest="2026-08-03", rows=[
        _cand("005930", "삼성전자", stage=1),
        _cand("000660", "SK하이닉스", stage=4),
        {"ticker": "999990", "name": "봉부족", "market": "KOSDAQ", "stage": None},  # 후보 제외
    ])
    _stub(monkeypatch, store=store)
    resp = _app().get("/api/screener")  # scope 기본 = cached
    assert resp.status_code == 200
    data = resp.json()
    assert data["scope"] == "cached" and data["as_of"] == "2026-08-03"
    tickers = [c["ticker"] for c in data["candidates"]]
    assert tickers == ["005930", "000660"]  # stage None 은 후보에서 제외
    assert data["total"] == 2 and data["universe_size"] == 3  # universe 는 None 포함
    assert data["market"] == "all" and data["catalog"] and "stages" in data["catalog"]


def test_cached_market_filter_kospi(monkeypatch):
    store = _FakeStore(latest="2026-08-03", rows=[
        _cand("005930", "삼성전자", market="KOSPI"),
        _cand("247540", "에코프로비엠", market="KOSDAQ"),
    ])
    _stub(monkeypatch, store=store)
    data = _app().get("/api/screener?market=kospi").json()
    assert data["scope"] == "cached" and data["market"] == "kospi"
    assert [c["ticker"] for c in data["candidates"]] == ["005930"]


def test_cached_empty_db_falls_back_to_live(monkeypatch):
    called = {}

    def _svc(client, *, market_iscd, size):
        called.update(iscd=market_iscd, size=size)
        return {"candidates": [_cand("005930", "삼성전자")], "catalog": {"stages": [], "periods": {}},
                "market_iscd": market_iscd, "size": size, "partial_failure": [], "as_of": "t"}

    _stub(monkeypatch, service=_svc, store=_FakeStore(latest=None))  # DB 비어있음
    data = _app().get("/api/screener").json()  # cached 기본이지만 DB 비면 live 폴백
    assert data["scope"] == "live" and called["iscd"] == "0000"
    assert [c["ticker"] for c in data["candidates"]] == ["005930"]


# ── scope=live (하위호환) ─────────────────────────────────────────────────────

def test_live_scope_uses_service(monkeypatch):
    def _svc(client, *, market_iscd, size):
        return {"candidates": [{"ticker": "005930", "name": "삼성전자", "stage": 1}],
                "catalog": {"stages": [], "periods": {}}, "market_iscd": market_iscd,
                "size": size, "partial_failure": [], "as_of": "t"}

    _stub(monkeypatch, service=_svc)
    resp = _app().get("/api/screener?scope=live&market=kospi200&size=20")
    assert resp.status_code == 200
    data = resp.json()
    assert data["scope"] == "live"
    assert data["candidates"][0]["name"] == "삼성전자"
    assert data["market"] == "kospi200" and data["market_iscd"] == "2001" and data["size"] == 20


def test_market_fallback_and_size_clamp(monkeypatch):
    captured = {}

    def _svc(client, *, market_iscd, size):
        captured.update(iscd=market_iscd, size=size)
        return {"candidates": [], "catalog": None, "market_iscd": market_iscd,
                "size": size, "partial_failure": [], "as_of": "t"}

    _stub(monkeypatch, service=_svc)
    # 불량 market → all("0000"), size 999 → 40 clamp
    resp = _app().get("/api/screener?scope=live&market=bogus&size=999")
    assert resp.status_code == 200
    assert captured["iscd"] == "0000" and captured["size"] == 40
    assert resp.json()["market"] == "all"


def test_size_min_clamp(monkeypatch):
    captured = {}
    _stub(monkeypatch, service=lambda client, *, market_iscd, size: captured.update(size=size) or {
        "candidates": [], "catalog": None, "market_iscd": market_iscd, "size": size,
        "partial_failure": [], "as_of": "t"})
    _app().get("/api/screener?scope=live&size=1")
    assert captured["size"] == 10  # 하한 clamp


def test_graceful_on_kis_failure(monkeypatch):
    def _boom(client, *, market_iscd, size):
        raise RuntimeError("kis down")

    _stub(monkeypatch, service=_boom)
    resp = _app().get("/api/screener?scope=live")
    assert resp.status_code == 200
    data = resp.json()
    assert data["candidates"] == [] and data["partial_failure"] == ["screener"]
    assert data["market"] == "all" and data["scope"] == "live"


def test_cached_kospi200_falls_back_to_live(monkeypatch):
    # kospi200 은 cached 에서 재현 불가(마스터에 편입정보 없음) → live 폴백
    called = {}

    def _svc(client, *, market_iscd, size):
        called.update(iscd=market_iscd)
        return {"candidates": [], "catalog": None, "market_iscd": market_iscd,
                "size": size, "partial_failure": [], "as_of": "t"}

    _stub(monkeypatch, service=_svc, store=_FakeStore(latest="2026-08-03", rows=[]))
    data = _app().get("/api/screener?market=kospi200").json()  # scope 기본 cached
    assert data["scope"] == "live" and called["iscd"] == "2001"
