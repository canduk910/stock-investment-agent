"""매크로 지표 API 라우트 테스트 — plan §5.

라우트가 집계기 결과를 JSON 으로 반환하고, IndicatorPoint 의 date(as_of)가
ISO 문자열로 직렬화되며, partial_failure 를 그대로 전달하는지 검증한다.
집계기와 키 로딩은 경계로 mock(실 API/키 불필요).
"""
from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

import api.main as main
from collectors.base import indicator_point


def _client(monkeypatch):
    monkeypatch.setattr(main, "fred_api_key", lambda: "KEY")
    return TestClient(main.app)


def test_health(monkeypatch):
    client = _client(monkeypatch)
    assert client.get("/api/health").json() == {"status": "ok"}


def test_macro_indicators_route_serializes_and_passes_partial_failure(monkeypatch):
    def fake_collect(key):
        assert key == "KEY"
        return {
            "indicators": {
                "t10y2y": indicator_point("T10Y2Y", 0.35, dt.date(2026, 7, 2), "FRED"),
                "fear_greed": None,
            },
            "partial_failure": ["fear_greed"],
        }

    monkeypatch.setattr(main, "collect_macro_indicators", fake_collect)
    client = _client(monkeypatch)

    resp = client.get("/api/macro/indicators")

    assert resp.status_code == 200
    body = resp.json()
    assert body["indicators"]["t10y2y"]["value"] == 0.35
    assert body["indicators"]["t10y2y"]["source"] == "FRED"
    assert body["indicators"]["t10y2y"]["as_of"] == "2026-07-02"  # date → ISO 문자열
    assert body["indicators"]["fear_greed"] is None
    assert body["partial_failure"] == ["fear_greed"]
