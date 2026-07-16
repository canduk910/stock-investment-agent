"""공포탐욕지수 수집기 테스트 — plan §3, T7.

fear-and-greed 래퍼(CNN 비공식). graceful: 성공 시 IndicatorPoint,
실패 시 예외를 삼키지 않되 None 반환(호출자가 partial_failure 기록).
라이브러리 호출을 경계로 mock한다.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from collectors import fear_greed


def test_fear_greed_success(monkeypatch, load_fixture):
    fixture = load_fixture("fear_greed_cnn")
    fake = SimpleNamespace(
        value=fixture["value"],
        description=fixture["description"],
        last_update=dt.datetime.fromisoformat(fixture["last_update"]),
    )
    monkeypatch.setattr(fear_greed, "_cnn_get", lambda: fake)

    point = fear_greed.fetch_fear_greed()

    assert point["key"] == "fear_greed"
    assert point["value"] == 62.5
    assert point["as_of"] == dt.date(2026, 7, 3)
    assert point["source"] == "CNN"


def test_fear_greed_failure_returns_none_without_raising(monkeypatch):
    """스크래핑 실패 시 예외를 삼키지 않되 None을 반환해 파이프라인을 죽이지 않는다."""
    def boom():
        raise RuntimeError("CNN 페이지 구조 변경")

    monkeypatch.setattr(fear_greed, "_cnn_get", boom)

    point = fear_greed.fetch_fear_greed()

    assert point is None  # 호출자가 partial_failure에 기록


# ── 월단위 히스토리(CNN graphdata best-effort) ───────────────────────────────

def _ms(y, m, d):
    return dt.datetime(y, m, d, tzinfo=dt.timezone.utc).timestamp() * 1000


def test_fear_greed_history_resamples_monthly_last(monkeypatch):
    # 일단위 graphdata → 월별 마지막 관측(과거→현재).
    graph = {"fear_and_greed_historical": {"data": [
        {"x": _ms(2025, 10, 5), "y": 40.0},
        {"x": _ms(2025, 10, 28), "y": 45.0},  # 10월 마지막 → 45
        {"x": _ms(2025, 11, 15), "y": 55.0},
        {"x": _ms(2025, 12, 30), "y": 62.0},
    ]}}
    monkeypatch.setattr(fear_greed, "_cnn_graphdata", lambda: graph)

    points = fear_greed.fetch_fear_greed_history(months=12)

    assert points == [
        {"date": "2025-10-01", "value": 45.0},
        {"date": "2025-11-01", "value": 55.0},
        {"date": "2025-12-01", "value": 62.0},
    ]


def test_fear_greed_history_picks_month_latest_regardless_of_order(monkeypatch):
    # 소스가 월내 비오름차순으로 줘도 그 달의 '가장 나중(max x)' 관측을 선택(정렬 가정 비의존).
    graph = {"fear_and_greed_historical": {"data": [
        {"x": _ms(2025, 10, 28), "y": 45.0},  # 나중이지만 배열상 앞
        {"x": _ms(2025, 10, 5), "y": 40.0},   # 이른데 배열상 뒤 — 덮어써도 45 유지돼야
    ]}}
    monkeypatch.setattr(fear_greed, "_cnn_graphdata", lambda: graph)
    assert fear_greed.fetch_fear_greed_history(months=12) == [{"date": "2025-10-01", "value": 45.0}]


def test_fear_greed_history_failure_returns_none(monkeypatch):
    def boom():
        raise RuntimeError("graphdata 418")

    monkeypatch.setattr(fear_greed, "_cnn_graphdata", boom)
    assert fear_greed.fetch_fear_greed_history() is None  # graceful(라우트가 available:false)


def test_fear_greed_history_empty_returns_none(monkeypatch):
    monkeypatch.setattr(fear_greed, "_cnn_graphdata", lambda: {"fear_and_greed_historical": {"data": []}})
    assert fear_greed.fetch_fear_greed_history() is None
