"""전체 유니버스 배치 스캐너(scan_all) — 오케스트레이션·progress·graceful·upsert·counts.

경계(종목별 cycle fetch·유니버스 로딩·store)를 monkeypatch 로 대체하고 스캔 로직을 검증한다.
판정=코드(LLM 0)·네트워크 0(hermetic). 병렬이라 순서는 단정하지 않는다.
"""
from __future__ import annotations

import stock.screener_scan as scan


class FakeStore:
    def __init__(self):
        self.saved = None

    def upsert_scan(self, as_of_date, rows):
        self.saved = (as_of_date, list(rows))
        return len(rows)


_UNIVERSE = [
    {"ticker": "005930", "name": "삼성전자", "market": "KOSPI"},
    {"ticker": "000660", "name": "SK하이닉스", "market": "KOSPI"},
    {"ticker": "247540", "name": "에코프로비엠", "market": "KOSDAQ"},
    {"ticker": "999990", "name": "봉부족", "market": "KOSDAQ"},   # 봉<40 → cycle None
    {"ticker": "111110", "name": "조회실패", "market": "KOSPI"},   # fetch 예외
]


def _cycle(stage):
    return {"stage": stage, "stage_name": f"단계{stage}", "arrangement": "단 > 중 > 장",
            "band_width_pct": 5.0, "band_direction": "확대", "bars_in_stage": 3}


def _patch(monkeypatch, *, universe=_UNIVERSE):
    cycles = {"005930": _cycle(1), "000660": _cycle(4), "247540": _cycle(6), "999990": None}

    def _fetch(client, ticker):
        if ticker == "111110":
            raise RuntimeError("kis fail")
        return cycles.get(ticker)

    monkeypatch.setattr(scan, "_fetch_cycle", _fetch)
    return universe


def test_scan_all_stores_rows_and_counts(monkeypatch):
    universe = _patch(monkeypatch)
    store = FakeStore()
    counts = scan.scan_all(object(), store, universe=universe, as_of_date="2026-08-03", concurrency=4)

    as_of, rows = store.saved
    assert as_of == "2026-08-03"
    by = {r["ticker"]: r for r in rows}
    # 전 종목 저장(실패·봉부족 포함)
    assert set(by) == {"005930", "000660", "247540", "999990", "111110"}
    # stage 산출 종목
    assert by["005930"]["stage"] == 1 and by["005930"]["stage_name"] == "단계1"
    assert by["005930"]["name"] == "삼성전자" and by["005930"]["market"] == "KOSPI"
    # 봉부족·조회실패는 stage None(판정 보류)
    assert by["999990"]["stage"] is None and by["111110"]["stage"] is None
    # 카운트
    assert counts["total"] == 5 and counts["scanned"] == 5
    assert counts["with_stage"] == 3   # 005930·000660·247540
    assert counts["failed"] == 1       # 111110(예외)
    assert counts["as_of_date"] == "2026-08-03" and counts["stored"] == 5


def test_scan_all_progress_callback(monkeypatch):
    universe = _patch(monkeypatch)
    seen = []
    scan.scan_all(object(), FakeStore(), universe=universe,
                  on_progress=lambda done, total, ticker: seen.append((done, total, ticker)),
                  as_of_date="2026-08-03", concurrency=2)
    # 종목당 1회, done 은 1..total(순서는 병렬이라 무관)
    assert len(seen) == 5
    assert {d for d, _, _ in seen} == {1, 2, 3, 4, 5}
    assert all(t == 5 for _, t, _ in seen)


def test_scan_all_default_universe_uses_common_stocks(monkeypatch):
    # universe 미지정 → common_stocks(load_stock_master()) 사용
    monkeypatch.setattr(scan, "load_stock_master", lambda: [
        {"ticker": "005930", "name": "삼성전자", "market": "KOSPI"},
        {"ticker": "005935", "name": "삼성전자우", "market": "KOSPI"},   # 우선주 → 필터
    ])
    monkeypatch.setattr(scan, "_fetch_cycle", lambda client, ticker: _cycle(1))
    store = FakeStore()
    counts = scan.scan_all(object(), store, as_of_date="2026-08-03")
    _, rows = store.saved
    assert [r["ticker"] for r in rows] == ["005930"]  # 우선주 제외됨
    assert counts["total"] == 1


def test_scan_all_empty_universe(monkeypatch):
    _patch(monkeypatch, universe=[])
    store = FakeStore()
    counts = scan.scan_all(object(), store, universe=[], as_of_date="2026-08-03")
    assert store.saved == ("2026-08-03", [])
    assert counts["total"] == 0 and counts["scanned"] == 0 and counts["stored"] == 0
