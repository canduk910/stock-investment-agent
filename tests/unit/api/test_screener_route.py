"""대순환 후보 스크리너 라우트 계약 테스트 — GET /api/screener (TDD Red→Green).

서비스(screen_grand_cycle)와 KIS 클라이언트 해석(_resolve_client)을 경계 mock 으로 대체하고,
market 화이트리스트 폴백·size clamp·항상 200 graceful 을 검증한다(파이프라인 자체는 test_screener).

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


def _stub_service(monkeypatch, fn):
    monkeypatch.setattr(screener, "_resolve_client", lambda user, db: object())
    monkeypatch.setattr(screener, "screen_grand_cycle", fn)


def test_screener_returns_service_result(monkeypatch):
    def _svc(client, *, market_iscd, size):
        return {
            "candidates": [{"ticker": "005930", "name": "삼성전자", "stage": 1}],
            "catalog": {"stages": [], "periods": {}},
            "market_iscd": market_iscd, "size": size, "partial_failure": [], "as_of": "t",
        }

    _stub_service(monkeypatch, _svc)
    resp = _app().get("/api/screener?market=kospi200&size=20")
    assert resp.status_code == 200
    data = resp.json()
    assert data["candidates"][0]["name"] == "삼성전자"  # 종목명 포함
    assert data["market"] == "kospi200" and data["market_iscd"] == "2001" and data["size"] == 20


def test_market_fallback_and_size_clamp(monkeypatch):
    captured = {}

    def _svc(client, *, market_iscd, size):
        captured.update(iscd=market_iscd, size=size)
        return {"candidates": [], "catalog": None, "market_iscd": market_iscd,
                "size": size, "partial_failure": [], "as_of": "t"}

    _stub_service(monkeypatch, _svc)
    # 불량 market → all("0000"), size 999 → 40 clamp
    resp = _app().get("/api/screener?market=bogus&size=999")
    assert resp.status_code == 200
    assert captured["iscd"] == "0000" and captured["size"] == 40
    assert resp.json()["market"] == "all"


def test_size_min_clamp(monkeypatch):
    captured = {}
    _stub_service(monkeypatch, lambda client, *, market_iscd, size: captured.update(size=size) or {
        "candidates": [], "catalog": None, "market_iscd": market_iscd, "size": size,
        "partial_failure": [], "as_of": "t"})
    _app().get("/api/screener?size=1")
    assert captured["size"] == 10  # 하한 clamp


def test_graceful_on_kis_failure(monkeypatch):
    def _boom(client, *, market_iscd, size):
        raise RuntimeError("kis down")

    _stub_service(monkeypatch, _boom)
    resp = _app().get("/api/screener")
    assert resp.status_code == 200
    data = resp.json()
    assert data["candidates"] == [] and data["partial_failure"] == ["screener"]
    assert data["market"] == "all"  # 기본 market
