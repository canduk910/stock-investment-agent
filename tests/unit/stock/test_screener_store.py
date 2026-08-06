"""스크리너 스캔 결과 store(SQL 공동 DB) — upsert(같은날 갱신)·latest·list(market/stage 필터).

인메모리 SQLite(StaticPool) 주입으로 hermetic. 현재가/등락률 미저장(무캐시 원칙1) 계약 잠금.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from infra.db import Base, import_models
from stock.screener_store import ScreenerResultStore


@pytest.fixture
def store():
    import_models()  # ScreenerResultRow 등록
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False)
    return ScreenerResultStore(session_factory=sf)


def _row(ticker, name, market="KOSPI", stage=1, **extras):
    row = {
        "ticker": ticker, "name": name, "market": market,
        "stage": stage, "stage_name": "안정 상승기", "arrangement": "단 > 중 > 장",
        "band_width_pct": 12.3, "band_direction": "확대", "bars_in_stage": 7,
        "market_cap": 4_500_000.0, "roe": 10.85, "net_income_growth": 15.0,
        "debt_ratio": 40.0, "avg_per": 17.0, "spark": [100.0, 105.5, 110.0],
    }
    row.update(extras)
    return row


def test_upsert_and_list_latest(store):
    store.upsert_scan("2026-08-03", [_row("005930", "삼성전자"), _row("000660", "SK하이닉스", stage=4)])
    assert store.latest_as_of() == "2026-08-03"
    rows = store.list_results()  # 최근 스캔 기본
    by = {r["ticker"]: r for r in rows}
    assert by["005930"]["name"] == "삼성전자" and by["005930"]["stage"] == 1
    assert by["005930"]["stage_name"] == "안정 상승기" and by["005930"]["band_width_pct"] == 12.3
    # 후보 강화 스냅샷(시총 정렬키·재무 원천·avg_per)이 왕복
    assert by["005930"]["market_cap"] == 4_500_000.0 and by["005930"]["roe"] == 10.85
    assert by["005930"]["avg_per"] == 17.0
    # 현재가·현재 PER 은 저장·반환하지 않는다(무캐시 원칙1 — 서빙이 라이브)
    assert "price" not in by["005930"] and "per" not in by["005930"]


def test_spark_round_trips(store):
    store.upsert_scan("2026-08-03", [_row("005930", "삼성전자", spark=[100.0, 110.25, 121.5])])
    r = store.list_results()[0]
    assert r["spark"] == [100.0, 110.25, 121.5]  # 콤마 조인 저장 → 리스트 복원


def test_spark_empty_is_none(store):
    store.upsert_scan("2026-08-03", [_row("005930", "삼성전자", spark=None)])
    assert store.list_results()[0]["spark"] is None


def test_upsert_same_day_replaces(store):
    store.upsert_scan("2026-08-03", [_row("005930", "삼성전자", stage=1)])
    store.upsert_scan("2026-08-03", [_row("005930", "삼성전자", stage=4)])  # 같은 날 재스캔 = 갱신
    rows = store.list_results("2026-08-03")
    assert len(rows) == 1 and rows[0]["stage"] == 4  # 중복 아님·최신값


def test_latest_picks_newest_date(store):
    store.upsert_scan("2026-08-01", [_row("005930", "삼성전자")])
    store.upsert_scan("2026-08-03", [_row("005930", "삼성전자", stage=4)])
    assert store.latest_as_of() == "2026-08-03"
    assert store.list_results()[0]["stage"] == 4  # 기본 = 최신 스캔일


def test_list_market_filter(store):
    store.upsert_scan("2026-08-03", [
        _row("005930", "삼성전자", market="KOSPI"),
        _row("247540", "에코프로비엠", market="KOSDAQ"),
    ])
    kospi = store.list_results(market="KOSPI")
    assert [r["ticker"] for r in kospi] == ["005930"]
    kosdaq = store.list_results(market="KOSDAQ")
    assert [r["ticker"] for r in kosdaq] == ["247540"]


def test_list_stage_filter(store):
    store.upsert_scan("2026-08-03", [
        _row("005930", "삼성전자", stage=1),
        _row("000660", "SK하이닉스", stage=4),
    ])
    assert [r["ticker"] for r in store.list_results(stage=1)] == ["005930"]
    assert [r["ticker"] for r in store.list_results(stage=4)] == ["000660"]


def test_stage_none_is_stored(store):
    # 봉<40·조회실패 종목도 stage=None 으로 저장(서빙이 후보에서 제외 결정)
    store.upsert_scan("2026-08-03", [{"ticker": "999990", "name": "봉부족", "market": "KOSDAQ",
                                       "stage": None, "stage_name": None, "arrangement": None,
                                       "band_width_pct": None, "band_direction": None, "bars_in_stage": None}])
    rows = store.list_results()
    assert len(rows) == 1 and rows[0]["stage"] is None and rows[0]["ticker"] == "999990"


def test_empty_store(store):
    assert store.latest_as_of() is None
    assert store.list_results() == []
