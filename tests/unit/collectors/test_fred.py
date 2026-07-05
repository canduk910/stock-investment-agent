"""FRED 수집기 테스트 — plan §3, T5.

FRED REST(observations)만 responses로 mock. 최신 non-NaN 관측 선택·정규화는
실제 코드로 통과. 공통 반환은 IndicatorPoint {key, value:float, as_of:date, source}.
"""
from __future__ import annotations

import datetime as dt

import responses

from collectors import fred

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"


@responses.activate
def test_fetch_fred_series_picks_latest_non_nan(load_fixture):
    """마지막 관측이 '.'(결측)이면 그 이전의 유효 관측을 선택한다."""
    responses.add(responses.GET, FRED_URL, json=load_fixture("fred_T10Y2Y"), status=200)

    point = fred.fetch_fred_series("T10Y2Y", api_key="KEY")

    assert point["key"] == "T10Y2Y"
    assert point["value"] == 0.42  # 07-03은 '.'이므로 07-02
    assert point["as_of"] == dt.date(2026, 7, 2)
    assert point["source"] == "FRED"
    # [P2] 모멘텀 확장용 훅
    assert "prev_value" in point


@responses.activate
def test_fetch_t10y2y_wrapper_uses_series_id(load_fixture):
    responses.add(responses.GET, FRED_URL, json=load_fixture("fred_T10Y2Y"), status=200)
    point = fred.fetch_t10y2y(api_key="KEY")
    assert point["key"] == "T10Y2Y"
    # 요청 쿼리에 series_id가 실렸는지 (경계 검증)
    assert "series_id=T10Y2Y" in responses.calls[0].request.url


@responses.activate
def test_fred_wrappers_series_ids(load_fixture):
    """4종 래퍼가 올바른 series_id를 쓰는지."""
    expected = {
        fred.fetch_hy_spread: "BAMLH0A0HYM2",
        fred.fetch_dollar_index: "DTWEXBGS",
        fred.fetch_gdp: "GDP",
    }
    for func, series_id in expected.items():
        responses.reset()
        responses.add(responses.GET, FRED_URL, json=load_fixture("fred_T10Y2Y"), status=200)
        func(api_key="KEY")
        assert f"series_id={series_id}" in responses.calls[0].request.url
