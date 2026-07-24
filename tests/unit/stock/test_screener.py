"""대순환 후보 종목 스크리너 서비스 — 유니버스(랭킹) + 종목별 일봉 → 단계 판정.

경계(랭킹·일봉)를 monkeypatch 로 대체하고 오케스트레이션·단계 계산·partial_failure·graceful 을 검증한다.
판정=코드(LLM 0)·네트워크 0(hermetic).
"""
from __future__ import annotations

import stock.screener as screener


def _rising_closes(n=60):
    """정배열(장기상승) 유도용 완만 상승 종가 — stage 산출 확인."""
    return [100.0 + i * 1.5 for i in range(n)]


def _candles(closes):
    return {"candles": [{"date": f"202601{str(i + 1).zfill(2)}"[:8], "close": c} for i, c in enumerate(closes)]}


_UNIVERSE = [
    {"ticker": "005930", "name": "삼성전자", "rank": 1, "price": 78000.0, "change_rate": 1.2, "market_cap": 4.65e8},
    {"ticker": "000660", "name": "SK하이닉스", "rank": 2, "price": 180000.0, "change_rate": -0.8, "market_cap": 1.3e8},
    {"ticker": "999999", "name": "봉부족주", "rank": 3, "price": 1000.0, "change_rate": 0.0, "market_cap": 1000.0},
]


def _patch(monkeypatch, *, universe=_UNIVERSE, charts=None, fail=()):
    monkeypatch.setattr(screener.ranking, "market_cap_rank", lambda client, iscd="0000": list(universe))

    def _fetch(client, ticker, *, period="D", start_date, end_date, adj_price="0"):
        if ticker in fail:
            raise RuntimeError("kis fail")
        return charts.get(ticker, {"candles": []})

    monkeypatch.setattr(screener.chart, "fetch_chart_series", _fetch)


def test_screen_returns_candidates_with_names_and_stages(monkeypatch):
    charts = {
        "005930": _candles(_rising_closes(60)),   # 충분한 봉 → stage 산출
        "000660": _candles(_rising_closes(60)),
        "999999": _candles(_rising_closes(20)),    # 봉<40 → stage None
    }
    _patch(monkeypatch, charts=charts)
    out = screener.screen_grand_cycle(object(), market_iscd="0000", size=30)
    assert set(out.keys()) >= {"candidates", "catalog", "market_iscd", "size", "partial_failure", "as_of"}
    c = {x["ticker"]: x for x in out["candidates"]}
    # 종목명 반드시 포함(사용자 핵심 요구)
    assert c["005930"]["name"] == "삼성전자" and c["000660"]["name"] == "SK하이닉스"
    # 정배열 상승 → stage 1(안정상승기) 계열, band 필드 존재
    assert c["005930"]["stage"] in (1, 6) and c["005930"]["stage_name"]
    assert "band_width_pct" in c["005930"] and "bars_in_stage" in c["005930"]
    # 봉 부족 종목은 stage None(판정 보류) — 크래시 없음
    assert c["999999"]["stage"] is None and c["999999"]["name"] == "봉부족주"
    # 6단계 라벨 카탈로그(프론트 SSOT) 전파
    assert out["catalog"] and "stages" in out["catalog"]


def test_screen_size_slices_universe(monkeypatch):
    charts = {u["ticker"]: _candles(_rising_closes(60)) for u in _UNIVERSE}
    _patch(monkeypatch, charts=charts)
    out = screener.screen_grand_cycle(object(), size=2)
    assert len(out["candidates"]) == 2  # 상위 2종목만


def test_screen_partial_failure_graceful(monkeypatch):
    charts = {u["ticker"]: _candles(_rising_closes(60)) for u in _UNIVERSE}
    _patch(monkeypatch, charts=charts, fail={"000660"})  # 한 종목 일봉 조회 실패
    out = screener.screen_grand_cycle(object())
    c = {x["ticker"]: x for x in out["candidates"]}
    # 실패 종목도 카드에 남되 stage None, partial_failure 에 기록
    assert c["000660"]["stage"] is None and c["000660"]["name"] == "SK하이닉스"
    assert "000660" in out["partial_failure"]
    # 나머지는 정상
    assert c["005930"]["stage"] is not None


def test_screen_empty_universe(monkeypatch):
    _patch(monkeypatch, universe=[], charts={})
    out = screener.screen_grand_cycle(object())
    assert out["candidates"] == [] and out["partial_failure"] == []
