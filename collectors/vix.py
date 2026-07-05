"""VIX 수집기 — plan §3, T6.

야후파이낸스(^VIX)를 1차로, 실패 시 FRED VIXCLS로 폴백한다.
source에 성공 소스(yahoo|fred)를 기록해 소비자가 출처를 알 수 있게 한다.
"""
from __future__ import annotations

import datetime as dt

import requests

from collectors.base import indicator_point
from collectors.fred import fetch_fred_series

YAHOO_VIX_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX"


def _fetch_yahoo_vix() -> dict:
    resp = requests.get(YAHOO_VIX_URL, timeout=10)
    resp.raise_for_status()
    meta = resp.json()["chart"]["result"][0]["meta"]
    price = float(meta["regularMarketPrice"])
    as_of = dt.datetime.fromtimestamp(
        int(meta["regularMarketTime"]), tz=dt.timezone.utc
    ).date()
    return indicator_point("VIX", price, as_of, source="yahoo")


def fetch_vix(fred_api_key: str) -> dict:
    """VIX 조회. 야후 1차 실패 시 FRED VIXCLS 폴백."""
    try:
        return _fetch_yahoo_vix()
    except Exception:
        # 폴백: FRED VIXCLS. 키를 재라벨(source=fred)해 반환.
        point = fetch_fred_series("VIXCLS", fred_api_key)
        point["key"] = "VIX"
        point["source"] = "fred"
        return point
