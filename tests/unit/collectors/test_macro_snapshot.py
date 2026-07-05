"""매크로 지표 스냅샷 집계 테스트 — plan §5.1 (번들 패턴: 병렬 + partial_failure).

개별 수집기(fred/vix/fear_greed)를 경계로 mock 하고, 집계기가 6종을 모아
partial_failure 를 올바르게 기록하는지 검증한다(한 소스 실패가 전체를 죽이지 않음).
"""
from __future__ import annotations

import datetime as dt

from collectors import macro_snapshot
from collectors.base import indicator_point


def _pt(key, value):
    return indicator_point(key, value, dt.date(2026, 7, 2), "TEST")


def _patch_all_ok(monkeypatch):
    monkeypatch.setattr(macro_snapshot.fred, "fetch_t10y2y", lambda k: _pt("T10Y2Y", 0.35))
    monkeypatch.setattr(macro_snapshot.fred, "fetch_hy_spread", lambda k: _pt("BAMLH0A0HYM2", 2.75))
    monkeypatch.setattr(macro_snapshot.fred, "fetch_dollar_index", lambda k: _pt("DTWEXBGS", 120.89))
    monkeypatch.setattr(macro_snapshot.fred, "fetch_gdp", lambda k: _pt("GDP", 31865.7))
    monkeypatch.setattr(macro_snapshot.vix, "fetch_vix", lambda fred_api_key: _pt("VIX", 16.59))
    monkeypatch.setattr(macro_snapshot.fear_greed, "fetch_fear_greed", lambda: _pt("fear_greed", 31.9))


def test_collect_macro_indicators_all_success(monkeypatch):
    _patch_all_ok(monkeypatch)

    result = macro_snapshot.collect_macro_indicators("KEY")

    assert set(result["indicators"].keys()) == {
        "t10y2y", "hy_spread", "dollar_index", "gdp", "vix", "fear_greed",
    }
    assert result["indicators"]["t10y2y"]["value"] == 0.35
    assert result["indicators"]["fear_greed"]["value"] == 31.9
    assert result["partial_failure"] == []


def test_collect_macro_indicators_partial_failure(monkeypatch):
    """한 소스가 예외/None 이어도 나머지는 채우고 partial_failure 에 기록한다(§5.1)."""
    _patch_all_ok(monkeypatch)

    def boom(k):
        raise RuntimeError("FRED down")

    monkeypatch.setattr(macro_snapshot.fred, "fetch_gdp", boom)
    monkeypatch.setattr(macro_snapshot.fear_greed, "fetch_fear_greed", lambda: None)  # graceful None

    result = macro_snapshot.collect_macro_indicators("KEY")

    assert result["indicators"]["t10y2y"]["value"] == 0.35   # 성공분 유지
    assert result["indicators"]["gdp"] is None               # 예외 → None
    assert result["indicators"]["fear_greed"] is None        # graceful None
    assert set(result["partial_failure"]) == {"gdp", "fear_greed"}
