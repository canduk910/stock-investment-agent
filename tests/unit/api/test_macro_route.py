"""매크로 지표 API 라우트 테스트 — plan §5.

라우트가 집계기 결과를 JSON 으로 반환하고, IndicatorPoint 의 date(as_of)가
ISO 문자열로 직렬화되며, partial_failure 를 그대로 전달하는지 검증한다.
집계기와 키 로딩은 경계로 mock(실 API/키 불필요).

GET /api/macro/regime 은 집계기(collect_macro_indicators)와 판정 엔진
(judge_regime)을 **둘 다 경계 mock** 하고, 그 사이의 매핑(수집기 키 → 엔진 키,
None/실패 제외, IndicatorPoint.value 추출)과 응답 shape 을 검증한다.
"""
from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

import api.main as main
from cache.local import LocalCache
from collectors.base import indicator_point


def _client(monkeypatch):
    monkeypatch.setattr(main, "fred_api_key", lambda: "KEY")
    # 히스토리 캐시는 모듈 전역이라 테스트 간 오염 방지 위해 매번 새 인스턴스 주입.
    monkeypatch.setattr(main, "_MACRO_HISTORY_CACHE", LocalCache())
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


# ── GET /api/macro/regime ────────────────────────────────────────────────────


def _snapshot(indicators, partial_failure):
    return {"indicators": indicators, "partial_failure": partial_failure}


class _JudgeSpy:
    """judge_regime 경계 mock — 호출 인자(엔진 입력 dict)를 포착하고 고정 판정 반환."""

    def __init__(self, result):
        self.result = result
        self.called_with = None
        self.previous_regime = "sentinel"

    def __call__(self, data, previous_regime=None):
        self.called_with = data
        self.previous_regime = previous_regime
        return self.result


def _fixed_judgement():
    # 엔진 반환 계약(2축)과 동일한 shape (소비자 의존). 실제 엔진이 이 raw_data 로
    # 산출하는 값과 정합: 경기 악화(yield_spread<0) + 심리 공포(vix>28) → 수축.
    # recommended_cash_ratio·params 는 REGIME_PARAMS["수축"] 단일 출처(cash 20).
    # key_drivers 는 (label, axis∈{경기,심리}, direction∈{양호,악화,탐욕,공포}) tuple 리스트.
    return {
        "regime": "수축",
        "recommended_cash_ratio": 20,
        "confidence": "high",
        "axes": {
            "cycle": {"score": -1, "sign": "악화"},
            "sentiment": {"score": -1, "sign": "공포"},
        },
        "key_drivers": [
            ("장단기 금리차 역전", "경기", "악화"),
            ("변동성 급등", "심리", "공포"),
        ],
        "params": {"cash": 20},  # 국면은 현금비중만(항목3 — single_cap/per_max/pbr_max 폐기)
        "vix_panic": False,
        "missing_indicators": [],
        "raw_data": {"yield_spread": -0.1, "hy_spread": 4.0, "vix": 30.0, "fear_greed": 55},
    }


def test_macro_regime_maps_collector_keys_to_engine_keys_and_extracts_values(monkeypatch):
    # 4지표 전부 수집 성공 → 엔진 입력은 엔진 키(yield_spread…)로 매핑되고 값은 .value.
    def fake_collect(key):
        assert key == "KEY"  # fred_api_key 경계 통과 확인
        return _snapshot(
            {
                "t10y2y": indicator_point("T10Y2Y", -0.1, dt.date(2026, 7, 2), "FRED"),
                "hy_spread": indicator_point("hy_spread", 4.0, dt.date(2026, 7, 2), "FRED"),
                "vix": indicator_point("VIX", 30.0, dt.date(2026, 7, 2), "Yahoo"),
                "fear_greed": indicator_point("fear_greed", 55, dt.date(2026, 7, 2), "CNN"),
                # 국면과 무관한 지표는 수집돼도 엔진 입력에서 제외된다.
                "dollar_index": indicator_point("DTWEXBGS", 103.0, dt.date(2026, 7, 2), "FRED"),
                "gdp": indicator_point("GDP", 27000.0, dt.date(2026, 4, 1), "FRED"),
            },
            partial_failure=[],
        )

    spy = _JudgeSpy(_fixed_judgement())
    monkeypatch.setattr(main, "collect_macro_indicators", fake_collect)
    monkeypatch.setattr(main, "judge_regime", spy)
    client = _client(monkeypatch)

    resp = client.get("/api/macro/regime")

    assert resp.status_code == 200
    # 엔진에는 정확히 4지표가 엔진 키로만 전달(t10y2y→yield_spread), 무관 지표 제외.
    assert spy.called_with == {
        "yield_spread": -0.1,
        "hy_spread": 4.0,
        "vix": 30.0,
        "fear_greed": 55,
    }
    # 현재값 캐시 미경유 — previous_regime 없이 호출.
    assert spy.previous_regime is None


def test_macro_regime_response_includes_judgement_indicators_used_and_partial_failure(monkeypatch):
    def fake_collect(key):
        return _snapshot(
            {
                "t10y2y": indicator_point("T10Y2Y", -0.1, dt.date(2026, 7, 2), "FRED"),
                "hy_spread": indicator_point("hy_spread", 4.0, dt.date(2026, 7, 2), "FRED"),
                "vix": indicator_point("VIX", 30.0, dt.date(2026, 7, 2), "Yahoo"),
                "fear_greed": indicator_point("fear_greed", 55, dt.date(2026, 7, 2), "CNN"),
            },
            partial_failure=[],
        )

    monkeypatch.setattr(main, "collect_macro_indicators", fake_collect)
    monkeypatch.setattr(main, "judge_regime", _JudgeSpy(_fixed_judgement()))
    client = _client(monkeypatch)

    body = client.get("/api/macro/regime").json()

    # 판정 계약 전개(소비자 의존 키, 2축).
    assert body["regime"] == "수축"
    assert body["recommended_cash_ratio"] == 20
    assert body["confidence"] == "high"
    assert body["params"] == {"cash": 20}  # 현금비중만(항목3)
    # axes(dict)·vix_panic(bool) 그대로 전개. 구 votes·override 는 제거됐다.
    assert body["axes"]["cycle"] == {"score": -1, "sign": "악화"}
    assert body["axes"]["sentiment"] == {"score": -1, "sign": "공포"}
    assert body["vix_panic"] is False
    assert "votes" not in body
    assert "override" not in body
    # key_drivers tuple(label, axis, direction) 은 JSON 배열로 직렬화된다.
    assert body["key_drivers"][0] == ["장단기 금리차 역전", "경기", "악화"]
    # 엔진에 실제 사용된 값(엔진 키 → value).
    assert body["indicators_used"] == {
        "yield_spread": -0.1,
        "hy_spread": 4.0,
        "vix": 30.0,
        "fear_greed": 55,
    }
    assert body["partial_failure"] == []


def test_macro_regime_includes_indicator_breakdown(monkeypatch):
    # 판정근거 카드용 breakdown — 값 + 구간(양호/중립/악화·탐욕/중립/공포) + 축·임계·단위·출처.
    # judge_regime 은 mock 이지만 regime_breakdown 은 실값으로 동작(엔진 SSOT 분류).
    def fake_collect(key):
        return _snapshot(
            {
                "t10y2y": indicator_point("T10Y2Y", -0.1, dt.date(2026, 7, 2), "FRED"),
                "hy_spread": indicator_point("hy_spread", 4.0, dt.date(2026, 7, 2), "FRED"),
                "vix": indicator_point("VIX", 30.0, dt.date(2026, 7, 2), "Yahoo"),
                # fear_greed 누락 → 카드는 나오되 value/zone None.
            },
            partial_failure=["fear_greed"],
        )

    monkeypatch.setattr(main, "collect_macro_indicators", fake_collect)
    monkeypatch.setattr(main, "judge_regime", _JudgeSpy(_fixed_judgement()))
    client = _client(monkeypatch)

    bd = client.get("/api/macro/regime").json()["indicator_breakdown"]
    assert [d["key"] for d in bd] == ["yield_spread", "hy_spread", "vix", "fear_greed"]  # 경기→심리
    by = {d["key"]: d for d in bd}
    assert by["yield_spread"]["value"] == -0.1 and by["yield_spread"]["zone"] == "악화"
    assert by["hy_spread"]["zone"] == "중립"
    assert by["vix"]["value"] == 30.0 and by["vix"]["zone"] == "공포" and by["vix"]["axis"] == "심리"
    # 누락 지표도 카드로 노출(데이터 없음).
    assert by["fear_greed"]["value"] is None and by["fear_greed"]["zone"] is None
    # 각 카드에 임계·단위·출처(차트 가이드·표시용).
    assert by["yield_spread"]["thresholds"] == {"lo": 0.0, "hi": 0.5}
    assert all(d["source"] and "unit" in d for d in bd)


# ── GET /api/macro/indicators/{key}/history ──────────────────────────────────

def test_macro_history_fred_returns_monthly_points(monkeypatch):
    monkeypatch.setattr(
        main, "fetch_fred_series_history",
        lambda series_id, api_key, months=12: [
            {"date": "2025-11-01", "value": 18.0},
            {"date": "2025-12-01", "value": 20.5},
        ],
    )
    client = _client(monkeypatch)
    body = client.get("/api/macro/indicators/vix/history").json()
    assert body["key"] == "vix" and body["available"] is True
    assert body["points"] == [
        {"date": "2025-11-01", "value": 18.0},
        {"date": "2025-12-01", "value": 20.5},
    ]
    # 표시 메타(라벨/단위/출처/임계) — 카드·차트가 소비.
    assert body["label"] == "VIX 변동성"
    assert body["thresholds"] == {"lo": 14.0, "hi": 28.0}
    assert "source" in body and "unit" in body


def test_macro_history_fear_greed_unavailable_is_graceful(monkeypatch):
    # CNN graphdata 실패/미지원 → available:false + note(항상 200).
    monkeypatch.setattr(main, "fetch_fear_greed_history", lambda months=12: None)
    client = _client(monkeypatch)
    resp = client.get("/api/macro/indicators/fear_greed/history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False and body["points"] == []
    assert "note" in body


def test_macro_history_unknown_key_400(monkeypatch):
    # 판정 4지표가 아닌 키(dollar_index)는 400 — 잘못된 조회 차단.
    client = _client(monkeypatch)
    assert client.get("/api/macro/indicators/dollar_index/history").status_code == 400


def test_macro_history_caches_available(monkeypatch):
    calls = {"n": 0}

    def counting(series_id, api_key, months=12):
        calls["n"] += 1
        return [{"date": "2025-12-01", "value": 0.4}]

    monkeypatch.setattr(main, "fetch_fred_series_history", counting)
    client = _client(monkeypatch)
    client.get("/api/macro/indicators/yield_spread/history")
    client.get("/api/macro/indicators/yield_spread/history")  # 캐시 히트
    assert calls["n"] == 1  # 확정 과거값 캐시 → 수집기 1회만


def test_macro_history_clamps_and_forwards_and_keys_by_months(monkeypatch):
    # months 가 (1) 수집기로 그대로 전달되고 (2) 1..60 으로 클램프되며 (3) 캐시 키가 months 별로 분리되는지.
    # 셋 다 한 번에: months 별로 키가 다르면 수집기가 매번 호출되고, seen 이 전달·클램프 값을 증명한다.
    seen = []

    def cap(series_id, api_key, months=12):
        seen.append(months)
        return [{"date": "2025-12-01", "value": 0.4}]

    monkeypatch.setattr(main, "fetch_fred_series_history", cap)
    client = _client(monkeypatch)  # 새 캐시 1개 공유(3 요청)
    client.get("/api/macro/indicators/vix/history?months=6")
    client.get("/api/macro/indicators/vix/history?months=0")     # → 1 클램프
    client.get("/api/macro/indicators/vix/history?months=999")   # → 60 클램프
    # 키가 months 를 포함하므로 3번 다 캐시 미스 → 수집기 3회, 전달·클램프 값 그대로.
    assert seen == [6, 1, 60]


def test_macro_history_unavailable_not_cached(monkeypatch):
    calls = {"n": 0}

    def failing(months=12):
        calls["n"] += 1
        return None

    monkeypatch.setattr(main, "fetch_fear_greed_history", failing)
    client = _client(monkeypatch)
    client.get("/api/macro/indicators/fear_greed/history")
    client.get("/api/macro/indicators/fear_greed/history")  # 불가 응답은 미저장 → 재조회
    assert calls["n"] == 2


def test_macro_regime_excludes_none_and_missing_points_records_partial_failure(monkeypatch):
    # hy_spread 는 None(수집 실패), fear_greed 는 IndicatorPoint 이지만 value=None,
    # vix 는 아예 키 부재 → 셋 다 엔진 입력에서 제외 + partial_failure(엔진 키) 기록.
    def fake_collect(key):
        return _snapshot(
            {
                "t10y2y": indicator_point("T10Y2Y", -0.1, dt.date(2026, 7, 2), "FRED"),
                "hy_spread": None,
                "fear_greed": indicator_point("fear_greed", None, None, "CNN"),
            },
            partial_failure=["hy_spread", "fear_greed"],
        )

    spy = _JudgeSpy(_fixed_judgement())
    monkeypatch.setattr(main, "collect_macro_indicators", fake_collect)
    monkeypatch.setattr(main, "judge_regime", spy)
    client = _client(monkeypatch)

    body = client.get("/api/macro/regime").json()

    # 엔진 입력엔 성공한 yield_spread 만.
    assert spy.called_with == {"yield_spread": -0.1}
    assert body["indicators_used"] == {"yield_spread": -0.1}
    # 국면 4지표 중 사용 못 한 것(엔진 키)만 partial_failure 로.
    assert set(body["partial_failure"]) == {"hy_spread", "vix", "fear_greed"}


def test_macro_regime_passes_vix_panic_flag_through(monkeypatch):
    # vix_panic 은 블랭킷 오버라이드가 아니라 표시 플래그다(2축 판정은 정상 수행).
    # VIX 40 단독(다른 3지표 누락): 심리 공포로 점수화되고 vix_panic=True 가 그대로 전개된다.
    vix_panic_judgement = {
        "regime": "회복",
        "recommended_cash_ratio": 40,
        "confidence": "medium",
        "axes": {
            "cycle": {"score": 0, "sign": "중립"},
            "sentiment": {"score": -1, "sign": "공포"},
        },
        "key_drivers": [("변동성 급등", "심리", "공포")],
        "params": {"cash": 40},  # 현금비중만(항목3)
        "vix_panic": True,
        "missing_indicators": ["yield_spread", "hy_spread", "fear_greed"],
        "raw_data": {"vix": 40.0},
    }

    def fake_collect(key):
        return _snapshot(
            {"vix": indicator_point("VIX", 40.0, dt.date(2026, 7, 2), "Yahoo")},
            partial_failure=["t10y2y", "hy_spread", "fear_greed"],
        )

    monkeypatch.setattr(main, "collect_macro_indicators", fake_collect)
    monkeypatch.setattr(main, "judge_regime", _JudgeSpy(vix_panic_judgement))
    client = _client(monkeypatch)

    body = client.get("/api/macro/regime").json()

    assert body["vix_panic"] is True
    assert body["axes"]["sentiment"] == {"score": -1, "sign": "공포"}
    # 구 votes·override 키는 응답에 없다(엔진 계약에서 폐기).
    assert "votes" not in body
    assert "override" not in body
    assert body["key_drivers"] == [["변동성 급등", "심리", "공포"]]
    assert body["indicators_used"] == {"vix": 40.0}


# ── GET /api/macro/regime/history (국면 이동 궤적) ─────────────────────────────

# 월별 지표(2개월): 1월 전지표 양호/탐욕 → 확장, 2월 전지표 악화/공포 → 수축.
_FRED_HISTORY = {
    "T10Y2Y": [{"date": "2024-01-01", "value": 0.6}, {"date": "2024-02-01", "value": -0.2}],
    "BAMLH0A0HYM2": [{"date": "2024-01-01", "value": 2.5}, {"date": "2024-02-01", "value": 6.0}],
    "VIXCLS": [{"date": "2024-01-01", "value": 12.0}, {"date": "2024-02-01", "value": 30.0}],
}


def _fake_fred_hist(series_id, api_key, months=12):
    return _FRED_HISTORY[series_id]


def _fake_fg_hist(months=12):
    return [{"date": "2024-01-01", "value": 80.0}, {"date": "2024-02-01", "value": 20.0}]


def test_regime_history_reconstructs_monthly_trajectory(monkeypatch):
    # 판정은 실제 엔진(judge_regime)으로 재현 — 월별 (cycle,sentiment,regime) 정확·시간 오름차순.
    monkeypatch.setattr(main, "fetch_fred_series_history", _fake_fred_hist)
    monkeypatch.setattr(main, "fetch_fear_greed_history", _fake_fg_hist)
    client = _client(monkeypatch)

    body = client.get("/api/macro/regime/history?months=12").json()
    # months=12 → 분기 간격(step 3). 2개월 픽스처는 2점 이하라 표본화 안 함(월별 유지).
    assert body["available"] is True and body["months"] == 12
    assert body["interval"] == "quarterly" and body["step_months"] == 3
    assert body["partial_failure"] == []
    pts = body["points"]
    assert [p["date"] for p in pts] == ["2024-01-01", "2024-02-01"]
    assert (pts[0]["cycle_score"], pts[0]["sentiment_score"], pts[0]["regime"]) == (2, 2, "확장")
    assert pts[0]["recommended_cash_ratio"] == 60
    assert (pts[1]["cycle_score"], pts[1]["sentiment_score"], pts[1]["regime"]) == (-2, -2, "수축")


def test_regime_history_samples_quarterly_over_full_year(monkeypatch):
    # 12개월 전체 데이터 → 분기 간격(step 3)으로 표본화: 4점(03·06·09·12)·최근 앵커·오름차순.
    #   (엔진 재현 정확성은 build_trajectory 단위 테스트가 담당 — 여기선 표본화 계약만.)
    def fred12(series_id, api_key, months=12):
        base = {"T10Y2Y": 0.6, "BAMLH0A0HYM2": 2.5, "VIXCLS": 12.0}[series_id]
        return [{"date": f"2024-{m:02d}-01", "value": base} for m in range(1, 13)]

    monkeypatch.setattr(main, "fetch_fred_series_history", fred12)
    monkeypatch.setattr(
        main, "fetch_fear_greed_history",
        lambda months=12: [{"date": f"2024-{m:02d}-01", "value": 80.0} for m in range(1, 13)],
    )
    client = _client(monkeypatch)
    body = client.get("/api/macro/regime/history?months=12").json()
    assert body["interval"] == "quarterly" and body["step_months"] == 3
    assert [p["date"] for p in body["points"]] == [
        "2024-03-01", "2024-06-01", "2024-09-01", "2024-12-01",
    ]


def test_regime_history_clamps_months_forwarded_to_collectors(monkeypatch):
    seen = []
    monkeypatch.setattr(
        main, "fetch_fred_series_history",
        lambda series_id, api_key, months=12: seen.append(months) or [{"date": "2024-01-01", "value": 0.6}],
    )
    fg_seen = []
    monkeypatch.setattr(main, "fetch_fear_greed_history", lambda months=12: fg_seen.append(months) or None)
    client = _client(monkeypatch)
    b999 = client.get("/api/macro/regime/history?months=999").json()  # → 60 클램프
    b0 = client.get("/api/macro/regime/history?months=0").json()      # → 1 클램프
    # (1) FRED·(2) fear_greed 둘 다 클램프된 months 를 받고 (3) 응답 months 도 클램프 반영.
    assert 60 in seen and 1 in seen and max(seen) == 60
    assert 60 in fg_seen and 1 in fg_seen  # fear_greed 도 동일 클램프 전달
    assert b999["months"] == 60 and b0["months"] == 1


def test_regime_history_partial_when_fear_greed_missing(monkeypatch):
    # 공포탐욕(CNN) 결측이어도 심리축은 VIX 로 판정 → 궤적 유지, partial_failure 에 fear_greed 만.
    monkeypatch.setattr(main, "fetch_fred_series_history", _fake_fred_hist)
    monkeypatch.setattr(main, "fetch_fear_greed_history", lambda months=12: None)
    client = _client(monkeypatch)

    body = client.get("/api/macro/regime/history?months=12").json()
    assert body["available"] is True
    assert body["partial_failure"] == ["fear_greed"]
    # 1월 심리축은 VIX(12<14) 단독 → +1(fear_greed 없이도).
    assert body["points"][0]["sentiment_score"] == 1
    assert "fear_greed" in body["points"][0]["missing_indicators"]


def test_regime_history_all_fail_is_graceful(monkeypatch):
    monkeypatch.setattr(main, "fetch_fred_series_history", lambda series_id, api_key, months=12: None)
    monkeypatch.setattr(main, "fetch_fear_greed_history", lambda months=12: None)
    client = _client(monkeypatch)

    resp = client.get("/api/macro/regime/history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False and body["points"] == []
    assert "note" in body
    assert set(body["partial_failure"]) == {"yield_spread", "hy_spread", "vix", "fear_greed"}


def test_regime_history_caches_available(monkeypatch):
    calls = {"fred": 0}

    def counting_fred(series_id, api_key, months=12):
        calls["fred"] += 1
        return _FRED_HISTORY[series_id]

    monkeypatch.setattr(main, "fetch_fred_series_history", counting_fred)
    monkeypatch.setattr(main, "fetch_fear_greed_history", _fake_fg_hist)
    client = _client(monkeypatch)
    client.get("/api/macro/regime/history?months=12")
    client.get("/api/macro/regime/history?months=12")  # 캐시 히트
    assert calls["fred"] == 3  # 3 FRED 시계열 1회씩(두 번째 요청은 캐시)


def test_regime_history_excludes_current_in_progress_month(monkeypatch):
    # 진행 중 당월(부분 데이터)은 결정적으로 제외 — 라우트가 KST 당월을 빌더에 넘긴다.
    monkeypatch.setattr(main, "_current_month_kst", lambda: "2024-02")
    monkeypatch.setattr(main, "fetch_fred_series_history", _fake_fred_hist)  # 2024-01·02
    monkeypatch.setattr(main, "fetch_fear_greed_history", _fake_fg_hist)
    client = _client(monkeypatch)
    body = client.get("/api/macro/regime/history?months=12").json()
    assert [p["date"] for p in body["points"]] == ["2024-01-01"]  # 당월(2024-02) 제외


def test_regime_history_clean_collection_but_empty_is_graceful_and_uncached(monkeypatch):
    # 4지표 모두 수집 성공(partial_failure=[])이나 서로 다른 달만 커버 → 어느 달도 양축 동시 충족 못 함
    #   → available:false + note, 미저장(재요청 시 재수집). all-fail(partial_failure 가득) 과 구분되는 분기.
    calls = {"n": 0}

    def disjoint_fred(series_id, api_key, months=12):
        calls["n"] += 1
        if series_id == "VIXCLS":
            return [{"date": "2020-02-01", "value": 30.0}]  # 심리(vix)만, 2월
        return [{"date": "2020-01-01", "value": 0.6}]  # 경기(yield/hy), 1월

    monkeypatch.setattr(main, "fetch_fred_series_history", disjoint_fred)
    monkeypatch.setattr(main, "fetch_fear_greed_history", lambda months=12: [{"date": "2020-03-01", "value": 50.0}])
    client = _client(monkeypatch)
    body = client.get("/api/macro/regime/history?months=12").json()
    assert body["available"] is False and body["points"] == []
    assert body["partial_failure"] == []  # 수집은 전부 성공(빈 궤적은 정합 실패 탓)
    assert "note" in body
    before = calls["n"]
    client.get("/api/macro/regime/history?months=12")  # 미저장 → 재수집
    assert calls["n"] > before
