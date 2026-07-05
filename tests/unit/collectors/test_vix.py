"""VIX 수집기 테스트 — plan §3, T6.

야후(^VIX) 1차, 실패 시 FRED VIXCLS 폴백. 두 HTTP 경계를 responses로 mock하고
source에 성공 소스를 기록하는지 검증한다.
"""
from __future__ import annotations

import datetime as dt

import responses

from collectors import vix

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX"
FRED_URL = "https://api.stlouisfed.org/fred/series/observations"


@responses.activate
def test_vix_from_yahoo_primary(load_fixture):
    responses.add(responses.GET, YAHOO_URL, json=load_fixture("vix_yahoo"), status=200)

    point = vix.fetch_vix(fred_api_key="KEY")

    assert point["key"] == "VIX"
    assert point["value"] == 18.42
    assert point["source"] == "yahoo"


@responses.activate
def test_vix_falls_back_to_fred_when_yahoo_fails(load_fixture):
    """야후가 500이면 FRED VIXCLS로 폴백하고 source를 fred로 기록한다."""
    responses.add(responses.GET, YAHOO_URL, status=500)
    responses.add(responses.GET, FRED_URL, json=load_fixture("vix_fred_VIXCLS"), status=200)

    point = vix.fetch_vix(fred_api_key="KEY")

    assert point["key"] == "VIX"
    assert point["value"] == 19.55  # FRED 최신 관측
    assert point["as_of"] == dt.date(2026, 7, 3)
    assert point["source"] == "fred"
