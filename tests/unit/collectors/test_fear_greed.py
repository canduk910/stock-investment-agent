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
