"""대순환 후보 스크리너 라우트 계약 테스트 — GET /api/screener (TDD Red→Green).

두 경로: **scope=cached(기본)** = DB 최신 스캔(전체 유니버스) → **시총 역순 정렬** → stage 필터 →
표시 top-N **라이브 시세 enrich**(가격·현재 PER) + **재무 100점** / **scope=live** = 시총상위 라이브.
서비스(screen_grand_cycle)·store·KIS 클라이언트(_resolve_client)·라이브 시세(_live_price)를 경계
mock 으로 대체하고, 정렬·stage 필터·enrich·점수·market 폴백·size clamp·live 폴백·항상 200 검증.

안전·정책: 조회 전용(GET only, 주문 없음) · 현재가/PER 은 표시 top-N 만 라이브(무캐시 원칙1) ·
KIS 실패는 항상 200 + partial_failure · 재무점수·정렬·필터 판정=코드(LLM 0).
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


def _stub(monkeypatch, *, service=None, store=None, prices=None):
    monkeypatch.setattr(screener, "_resolve_client", lambda user, db: object())
    # 라이브 시세 enrich 경계 — prices[ticker] 반환(없으면 빈 dict).
    monkeypatch.setattr(screener, "_live_price", lambda client, t: (prices or {}).get(t, {}))
    if service is not None:
        monkeypatch.setattr(screener, "screen_grand_cycle", service)
    if store is not None:
        monkeypatch.setattr(screener, "_get_store", lambda: store)


def _cand(ticker, name, market="KOSPI", stage=1, market_cap=None,
          roe=None, net_income_growth=None, debt_ratio=None, avg_per=None, spark=None):
    return {"ticker": ticker, "name": name, "market": market, "stage": stage,
            "stage_name": "안정 상승기", "arrangement": "단 > 중 > 장",
            "band_width_pct": 5.0, "band_direction": "확대", "bars_in_stage": 3,
            "market_cap": market_cap, "roe": roe, "net_income_growth": net_income_growth,
            "debt_ratio": debt_ratio, "avg_per": avg_per, "spark": spark}


# ── scope=cached (기본) ───────────────────────────────────────────────────────

def test_cached_default_returns_db_results(monkeypatch):
    store = _FakeStore(latest="2026-08-03", rows=[
        _cand("005930", "삼성전자", stage=1, market_cap=4_500_000.0),
        _cand("000660", "SK하이닉스", stage=4, market_cap=900_000.0),
        {"ticker": "999990", "name": "봉부족", "market": "KOSDAQ", "stage": None},  # 후보 제외
    ])
    _stub(monkeypatch, store=store)
    resp = _app().get("/api/screener")  # scope 기본 = cached, stage 기본 = all
    assert resp.status_code == 200
    data = resp.json()
    assert data["scope"] == "cached" and data["as_of"] == "2026-08-03"
    tickers = [c["ticker"] for c in data["candidates"]]
    assert tickers == ["005930", "000660"]  # stage None 제외 + 시총 역순
    assert data["total"] == 2 and data["universe_size"] == 3  # universe 는 None 포함
    assert data["market"] == "all" and data["catalog"] and "stages" in data["catalog"]
    assert data["score_config"]["max_score"] == 100  # 재무점수 축 라벨 SSOT 전파


def test_cached_sorts_by_market_cap_desc(monkeypatch):
    store = _FakeStore(latest="2026-08-03", rows=[
        _cand("A", "소", stage=1, market_cap=100_000.0),
        _cand("B", "대", stage=1, market_cap=9_000_000.0),
        _cand("C", "무시총", stage=1, market_cap=None),   # 결측 → 맨 뒤
        _cand("D", "중", stage=1, market_cap=500_000.0),
    ])
    _stub(monkeypatch, store=store)
    data = _app().get("/api/screener").json()
    assert [c["ticker"] for c in data["candidates"]] == ["B", "D", "A", "C"]


def test_cached_stage_filter_rising_server_side(monkeypatch):
    store = _FakeStore(latest="2026-08-03", rows=[
        _cand("005930", "삼성전자", stage=1, market_cap=4_500_000.0),   # 상승(1)
        _cand("000660", "SK하이닉스", stage=4, market_cap=900_000.0),   # 하락(4)
        _cand("247540", "에코프로비엠", stage=6, market_cap=120_000.0),  # 상승(6)
    ])
    _stub(monkeypatch, store=store)
    data = _app().get("/api/screener?stage=rising").json()
    assert [c["ticker"] for c in data["candidates"]] == ["005930", "247540"]  # 1·6만
    assert data["stage"] == "rising" and data["total"] == 2


def test_cached_stage_filter_specific(monkeypatch):
    store = _FakeStore(latest="2026-08-03", rows=[
        _cand("005930", "삼성전자", stage=1, market_cap=4_500_000.0),
        _cand("000660", "SK하이닉스", stage=4, market_cap=900_000.0),
    ])
    _stub(monkeypatch, store=store)
    data = _app().get("/api/screener?stage=4").json()
    assert [c["ticker"] for c in data["candidates"]] == ["000660"]


def test_cached_enriches_live_price_and_computes_score(monkeypatch):
    store = _FakeStore(latest="2026-08-03", rows=[
        _cand("005930", "삼성전자", stage=1, market_cap=4_500_000.0,
              roe=20.0, net_income_growth=30.0, debt_ratio=30.0, avg_per=20.0, spark=[100.0, 110.0]),
    ])
    # 라이브 현재 PER 15 → per_vs_avg = (15-20)/20*100 = -25% → 밸류 축 저평가(만점)
    _stub(monkeypatch, store=store, prices={"005930": {"price": 232000.0, "change_rate": -1.2, "per": 15.0}})
    c = _app().get("/api/screener").json()["candidates"][0]
    assert c["price"] == 232000.0 and c["change_rate"] == -1.2 and c["per"] == 15.0  # 라이브 시세
    assert c["spark"] == [100.0, 110.0]                     # 스캔 저장 미니차트
    assert c["per_vs_avg"] == -25.0                          # 라이브 PER vs 저장 avg_per
    assert c["fin_score"] == 100                             # 4축 전부 만점(ROE20·성장30·부채30·저평가)
    assert any(a["key"] == "per_vs_avg" for a in c["fin_axes"])  # 밸류 축 포함(라이브 PER)


def test_cached_no_avg_per_uses_three_axis_score(monkeypatch):
    store = _FakeStore(latest="2026-08-03", rows=[
        _cand("005930", "삼성전자", stage=1, market_cap=4_500_000.0,
              roe=10.0, net_income_growth=10.0, debt_ratio=50.0, avg_per=None),  # avg_per 없음
    ])
    _stub(monkeypatch, store=store, prices={"005930": {"price": 1.0, "change_rate": 0.0, "per": 12.0}})
    c = _app().get("/api/screener").json()["candidates"][0]
    assert c["per_vs_avg"] is None
    assert all(a["key"] != "per_vs_avg" for a in c["fin_axes"])  # 밸류 축 제외(3축 재정규화)
    assert c["fin_score"] == round((18 + 18 + 18) / 75 * 100)    # 72


def test_cached_market_filter_kospi(monkeypatch):
    store = _FakeStore(latest="2026-08-03", rows=[
        _cand("005930", "삼성전자", market="KOSPI", market_cap=4_500_000.0),
        _cand("247540", "에코프로비엠", market="KOSDAQ", market_cap=120_000.0),
    ])
    _stub(monkeypatch, store=store)
    data = _app().get("/api/screener?market=kospi").json()
    assert data["scope"] == "cached" and data["market"] == "kospi"
    assert [c["ticker"] for c in data["candidates"]] == ["005930"]


def test_cached_empty_db_falls_back_to_live(monkeypatch):
    called = {}

    def _svc(client, *, market_iscd, size):
        called.update(iscd=market_iscd, size=size)
        return {"candidates": [_cand("005930", "삼성전자", market_cap=4_500_000.0)],
                "catalog": {"stages": [], "periods": {}},
                "market_iscd": market_iscd, "size": size, "partial_failure": [], "as_of": "t"}

    _stub(monkeypatch, service=_svc, store=_FakeStore(latest=None))  # DB 비어있음
    data = _app().get("/api/screener").json()  # cached 기본이지만 DB 비면 live 폴백
    assert data["scope"] == "live" and called["iscd"] == "0000"
    assert [c["ticker"] for c in data["candidates"]] == ["005930"]


# ── scope=live (하위호환) ─────────────────────────────────────────────────────

def test_live_scope_uses_service(monkeypatch):
    def _svc(client, *, market_iscd, size):
        return {"candidates": [{"ticker": "005930", "name": "삼성전자", "stage": 1, "market_cap": 4_500_000.0}],
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
