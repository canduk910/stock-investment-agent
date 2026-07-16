"""FRED 매크로 지표 수집기 — plan §3, T5.

FRED REST observations를 조회해 최신 non-NaN 관측을 IndicatorPoint로 반환한다.
REST를 직접 쓰는 이유: HTTP 경계를 responses로 mock하기 쉽다(fredapi 객체 대신).

series_id: 장단기금리차 T10Y2Y / HY스프레드 BAMLH0A0HYM2 / 달러지수 DTWEXBGS / GDP.
api_key는 infra.config.fred_api_key()를 통해 환경변수에서만 로드(호출자 주입).
"""
from __future__ import annotations

import datetime as dt

import requests

from collectors.base import indicator_point

FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"


def fetch_fred_series(series_id: str, api_key: str) -> dict:
    """FRED 시계열 최신 유효 관측 → IndicatorPoint.

    결측(value == '.')은 건너뛰고 가장 최근의 유효 관측을 고른다.
    prev_value에는 그 직전 유효 관측을 담아 모멘텀 확장(P2)을 돕는다.
    """
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
    }
    resp = requests.get(FRED_OBSERVATIONS_URL, params=params, timeout=10)
    resp.raise_for_status()
    observations = resp.json().get("observations", [])

    # 최신순으로 유효 관측만 추출
    valid = [
        (obs["date"], obs["value"])
        for obs in reversed(observations)
        if obs.get("value") not in (None, ".", "")
    ]
    if not valid:
        return indicator_point(series_id, None, None, "FRED")

    latest_date, latest_value = valid[0]
    prev_value = float(valid[1][1]) if len(valid) > 1 else None
    return indicator_point(
        key=series_id,
        value=float(latest_value),
        as_of=dt.date.fromisoformat(latest_date),
        source="FRED",
        prev_value=prev_value,
    )


def fetch_fred_series_history(
    series_id: str, api_key: str, months: int = 12, frequency: str = "m"
) -> list[dict]:
    """FRED 시계열 월단위 히스토리 → [{date, value}] (date 오름차순, 최근 months개).

    최근 `months`개월 범위를 frequency(기본 월 'm')로 다운샘플(FRED 기본 집계=평균).
    일단위 시리즈(T10Y2Y/BAMLH0A0HYM2/VIXCLS)를 월단위 12포인트로 요약한다. 결측('.')은 제외.
    히스토리는 **확정 과거값**이라 캐시 가능(라우트가 TTL 관리) — 현재값 무캐시 원칙1과 무관.
    """
    end = dt.date.today()
    start = end - dt.timedelta(days=31 * months + 10)  # months 개월 + 여유(경계 절삭 방지)
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start.isoformat(),
        "observation_end": end.isoformat(),
        "frequency": frequency,
    }
    resp = requests.get(FRED_OBSERVATIONS_URL, params=params, timeout=10)
    resp.raise_for_status()
    observations = resp.json().get("observations", [])
    points = [
        {"date": obs["date"], "value": float(obs["value"])}
        for obs in observations
        if obs.get("value") not in (None, ".", "")
    ]
    points.sort(key=lambda p: p["date"])  # date 오름차순(FRED 는 이미 오름차순이나 방어)
    return points[-months:]  # 최근 months 개(과거→현재)


def fetch_t10y2y(api_key: str) -> dict:
    """장단기 금리차(10년-2년)."""
    return fetch_fred_series("T10Y2Y", api_key)


def fetch_hy_spread(api_key: str) -> dict:
    """하이일드 신용 스프레드."""
    return fetch_fred_series("BAMLH0A0HYM2", api_key)


def fetch_dollar_index(api_key: str) -> dict:
    """달러지수(광범위 무역가중)."""
    return fetch_fred_series("DTWEXBGS", api_key)


def fetch_gdp(api_key: str) -> dict:
    """GDP(버핏지수 분모)."""
    return fetch_fred_series("GDP", api_key)
