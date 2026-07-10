"""api/deps.py — 국면 판정 매핑/빌더 SSOT + ticker 검증(IMP-06/IMP-02).

map_engine_input 은 macro_regime(live_judgement)·종목/워치리스트/리포트(build_judgement)가
공유하는 단일 매핑이다. 여기서 그 계약(키 매핑·부분실패 기록)을 직접 고정한다.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

import api.deps as deps


def _snapshot(**vals):
    # collect_macro_indicators 반환 형태: {"indicators": {collector_key: {"value": ...}|None}}.
    indicators = {k: (None if v is None else {"value": v}) for k, v in vals.items()}
    return {"indicators": indicators}


# ── map_engine_input(매핑 SSOT) ──────────────────────────────────────────────

def test_map_engine_input_maps_collector_to_engine_keys():
    snap = _snapshot(t10y2y=0.5, hy_spread=3.2, vix=18.0, fear_greed=55)
    engine_input, partial = deps.map_engine_input(snap)
    assert engine_input == {
        "yield_spread": 0.5, "hy_spread": 3.2, "vix": 18.0, "fear_greed": 55,
    }
    assert partial == []


def test_map_engine_input_records_missing_and_none():
    # 키 부재·present-but-None 은 판정 제외 + partial_failure 기록(임의 기본값 금지).
    snap = _snapshot(t10y2y=0.5, hy_spread=None)  # vix·fear_greed 키 부재
    engine_input, partial = deps.map_engine_input(snap)
    assert engine_input == {"yield_spread": 0.5}
    assert set(partial) == {"hy_spread", "vix", "fear_greed"}


def test_map_engine_input_excludes_non_regime_indicators():
    # dollar_index·gdp 는 §4 4지표가 아니므로 수집돼도 엔진 입력에 안 들어간다.
    snap = _snapshot(t10y2y=0.5, hy_spread=3.0, vix=15.0, fear_greed=50, dollar_index=104, gdp=2.1)
    engine_input, partial = deps.map_engine_input(snap)
    assert set(engine_input) == {"yield_spread", "hy_spread", "vix", "fear_greed"}
    assert partial == []


# ── build_judgement(빌더 SSOT — 매핑 소비) ───────────────────────────────────

def test_build_judgement_maps_then_judges(monkeypatch):
    # 수집기·키는 deps 경계에서 mock(실 FRED 미호출). map_engine_input 을 실제로 통과시킨다.
    monkeypatch.setattr(deps, "fred_api_key", lambda: "KEY")
    monkeypatch.setattr(
        deps, "collect_macro_indicators",
        lambda key: _snapshot(t10y2y=0.6, hy_spread=2.5, vix=13.0, fear_greed=80),
    )
    captured = {}

    def _judge(engine_input):
        captured["engine_input"] = engine_input
        return {"regime": "확장"}

    monkeypatch.setattr(deps, "judge_regime", _judge)

    judgement = deps.build_judgement()
    assert judgement == {"regime": "확장"}
    assert captured["engine_input"] == {
        "yield_spread": 0.6, "hy_spread": 2.5, "vix": 13.0, "fear_greed": 80,
    }


# ── assert_valid_ticker(IMP-02) ──────────────────────────────────────────────

def test_assert_valid_ticker_accepts_six_alnum():
    deps.assert_valid_ticker("005930")  # 예외 없음


@pytest.mark.parametrize("bad", ["12345", "1234567", "abc_de", "삼성", "", None])
def test_assert_valid_ticker_rejects_invalid(bad):
    with pytest.raises(HTTPException) as exc:
        deps.assert_valid_ticker(bad)
    assert exc.value.status_code == 400
