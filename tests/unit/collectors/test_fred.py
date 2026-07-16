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


# ── 월단위 히스토리(1년) — 카드 클릭 시 사용 ─────────────────────────────────

_HISTORY_JSON = {
    "observations": [
        {"date": "2025-08-01", "value": "0.30"},
        {"date": "2025-09-01", "value": "."},        # 결측 → 제외
        {"date": "2025-10-01", "value": "0.35"},
        {"date": "2025-11-01", "value": "0.40"},
        {"date": "2025-12-01", "value": "0.42"},
    ]
}


@responses.activate
def test_fetch_fred_series_history_monthly_ascending_excludes_nan():
    responses.add(responses.GET, FRED_URL, json=_HISTORY_JSON, status=200)

    points = fred.fetch_fred_series_history("T10Y2Y", api_key="KEY", months=12)

    # 결측('.') 제외 + date 오름차순(과거→현재).
    assert points == [
        {"date": "2025-08-01", "value": 0.30},
        {"date": "2025-10-01", "value": 0.35},
        {"date": "2025-11-01", "value": 0.40},
        {"date": "2025-12-01", "value": 0.42},
    ]
    # 히스토리 쿼리 파라미터(월단위 다운샘플·날짜 범위).
    url = responses.calls[0].request.url
    assert "series_id=T10Y2Y" in url and "frequency=m" in url
    assert "observation_start=" in url and "observation_end=" in url


@responses.activate
def test_fetch_fred_series_history_window_widens_with_months():
    # months 가 실제로 조회 창을 넓히는지 — 큰 months 일수록 observation_start 가 더 과거(작다).
    import urllib.parse

    def start_for(months):
        responses.reset()
        responses.add(responses.GET, FRED_URL, json={"observations": []}, status=200)
        fred.fetch_fred_series_history("T10Y2Y", api_key="KEY", months=months)
        qs = urllib.parse.urlparse(responses.calls[0].request.url).query
        return urllib.parse.parse_qs(qs)["observation_start"][0]

    assert start_for(3) > start_for(12)  # 3개월 창은 더 최근(문자열상 큼)


@responses.activate
def test_fetch_fred_series_history_caps_to_months():
    # 관측이 months 보다 많으면 최근 months 개만(과거→현재 끝이 최신).
    obs = [{"date": f"2025-{m:02d}-01", "value": str(m)} for m in range(1, 13)]  # 12개월
    responses.add(responses.GET, FRED_URL, json={"observations": obs}, status=200)
    points = fred.fetch_fred_series_history("VIXCLS", api_key="KEY", months=3)
    assert len(points) == 3
    assert [p["date"] for p in points] == ["2025-10-01", "2025-11-01", "2025-12-01"]
