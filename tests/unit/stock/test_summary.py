"""종목 정량요약 엔진 경계 테스트 — plan §6.5a, quant-engine-rules §4·§5 (TDD Red).

이 목록이 곧 스펙이다(tdd-workflow §정량 엔진). 테스트 이름 접미사(__keyset/__cagr/
__sorting/__valuation_label/__avg_per_gate/__rsi/__ma/__pos52w/__safety)로 스펙 근거를
추적한다. 국면 진입게이트(regime_gate)는 폐기(항목3).

절대 규칙: 테스트가 실패하면 구현을 고친다. 임계값 상수(VALUATION_BAND_PCT 등)를
테스트에 맞춰 바꾸지 않는다. avg_per/valuation_label 은 AVG_PER_VERIFIED 게이트가
꺼져 있으면(기본) 데이터가 충분해도 None(적대적 검증 critical — 틀린 라벨 > 결측).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from stock import constants
from stock.summary import (
    _cagr,
    _rsi,
    _valuation_label,
    build_stock_summary,
    forward_valuation,
)

CORE_KEYS = {
    "rev_cagr", "op_cagr", "current_per", "avg_per", "per_vs_avg",
    "valuation_label", "rsi", "ma20_gap_pct", "pos_52w_pct",
}


# ── 헬퍼: 재무/시세 입력 조각 ────────────────────────────────────────────────

def _income(rows):
    """rows = [(period, revenue, operating_income)] → normalize 계약 shape."""
    return [
        {"period": p, "revenue": rev, "operating_income": op, "net_income": None}
        for (p, rev, op) in rows
    ]


def _financials(income=None, ratio=None, year_end_prices=None):
    return {
        "income": income or [],
        "ratio": ratio or [],
        "year_end_prices": year_end_prices or {},
    }


def _valuation(**kw):
    base = {
        "ticker": "005930", "price": None, "change_rate": None, "per": None,
        "pbr": None, "eps": None, "bps": None, "week52_high": None,
        "week52_low": None, "market_cap": None, "as_of": None,
    }
    base.update(kw)
    return base


def _chart(closes):
    """오름차순 종가 리스트 → 캔들(날짜는 순번). 미정렬 검증용은 별도로 뒤집는다."""
    return {"ticker": "005930", "candles": [
        {"date": f"202401{i:02d}", "open": c, "high": c, "low": c, "close": c, "volume": 1000}
        for i, c in enumerate(closes, start=1)
    ]}


# ── 반환 키셋 고정 (macro _result 계약 복제) ─────────────────────────────────

def test_returns_exactly_9_core_keys__keyset():
    r = build_stock_summary(_valuation(), _financials(), _valuation(), _chart([]))
    assert CORE_KEYS <= set(r), "9개 핵심 키가 항상 존재해야 한다(누락=키삭제 아닌 None)"


def test_all_missing_inputs_no_crash_all_none__keyset():
    r = build_stock_summary({}, _financials(), _valuation(), {"candles": []})
    for k in CORE_KEYS:
        assert r[k] is None, f"{k} 는 데이터 부재 시 None 이어야 한다"


# ── CAGR 경계 (기초값 <=0·부호전환·연수부족 → None) ──────────────────────────

def test_rev_cagr_normal__cagr():
    fin = _financials(income=_income([("202112", 100, 10), ("202212", 110, 11), ("202312", 121, 12)]))
    r = build_stock_summary(_valuation(), fin, _valuation(), _chart([]))
    assert r["rev_cagr"] == pytest.approx(10.0, abs=0.05)  # (121/100)^(1/2)-1


def test_rev_cagr_base_zero_is_none__cagr():
    fin = _financials(income=_income([("202112", 0, 10), ("202212", 10, 11), ("202312", 20, 12)]))
    r = build_stock_summary(_valuation(), fin, _valuation(), _chart([]))
    assert r["rev_cagr"] is None  # 기초값 0 → CAGR 미정의


def test_op_cagr_sign_flip_is_none__cagr():
    # 영업이익 적자(-10)로 시작 → 부호전환, CAGR 미정의
    fin = _financials(income=_income([("202112", 100, -10), ("202212", 110, 5), ("202312", 121, 20)]))
    r = build_stock_summary(_valuation(), fin, _valuation(), _chart([]))
    assert r["op_cagr"] is None
    assert r["rev_cagr"] is not None  # 매출은 정상 계산(독립)


def test_cagr_too_few_years_is_none__cagr():
    fin = _financials(income=_income([("202212", 110, 11), ("202312", 121, 12)]))  # 2개(<3)
    r = build_stock_summary(_valuation(), fin, _valuation(), _chart([]))
    assert r["rev_cagr"] is None and r["op_cagr"] is None


def test_cagr_annualized_by_actual_year_span__cagr():
    # 2021→2024 는 3년 구간(중간 2022 존재, 2023 결측). 지수는 실제 연도차(3)여야 한다.
    fin = _financials(income=_income([("202112", 100, 10), ("202212", 110, 11), ("202412", 133.1, 12)]))
    r = build_stock_summary(_valuation(), fin, _valuation(), _chart([]))
    assert r["rev_cagr"] == pytest.approx(10.0, abs=0.05)  # (133.1/100)^(1/3)-1 = 0.1


def test_cagr_descending_input_same_as_ascending__sorting():
    # KIS 재무는 최신연도 우선(내림차순)으로 올 수 있다 — 정렬 후 first/last 를 취해야 부호가 안 뒤집힌다.
    fin = _financials(income=_income([("202312", 121, 12), ("202212", 110, 11), ("202112", 100, 10)]))
    r = build_stock_summary(_valuation(), fin, _valuation(), _chart([]))
    assert r["rev_cagr"] == pytest.approx(10.0, abs=0.05)


def test_cagr_ignores_interim_period__annual():
    # 라이브 발견: KIS 재무에 분기 interim(202603 등, 12월 아님)이 연간과 섞여 온다.
    # interim 을 연간 종점으로 쓰면 CAGR 이 왜곡된다 → 최빈 결산월(12) 연간만 사용해야 한다.
    fin = _financials(income=[
        {"period": "202112", "revenue": 100, "operating_income": 10, "net_income": None},
        {"period": "202212", "revenue": 110, "operating_income": 11, "net_income": None},
        {"period": "202312", "revenue": 121, "operating_income": 12, "net_income": None},
        {"period": "202603", "revenue": 9999, "operating_income": 9999, "net_income": None},  # 분기
    ])
    r = build_stock_summary(_valuation(), fin, _valuation(), _chart([]))
    assert r["rev_cagr"] == pytest.approx(10.0, abs=0.05)  # interim 무시 → 2021→2023


def test_cagr_uses_recent_window_only__annual():
    # 스펙 "5년 평균": 23년치가 와도 최근 FINANCIALS_LOOKBACK_YEARS 연간만(오래된 사업국면 제외).
    rows = [(f"20{y}12", v, v) for y, v in
            [(18, 50), (19, 60), (20, 70), (21, 80), (22, 90), (23, 100), (24, 110), (25, 121)]]
    fin = _financials(income=_income(rows))
    r = build_stock_summary(_valuation(), fin, _valuation(), _chart([]))
    n = constants.FINANCIALS_LOOKBACK_YEARS
    recent = rows[-n:]  # 최근 n개
    base, end = recent[0][1], recent[-1][1]
    span = int(recent[-1][0][:4]) - int(recent[0][0][:4])
    expected = ((end / base) ** (1.0 / span) - 1.0) * 100
    assert r["rev_cagr"] == pytest.approx(expected, abs=0.05)


def test_avg_per_ignores_interim_and_caps_window__avg_per_gate(monkeypatch):
    monkeypatch.setattr(constants, "AVG_PER_VERIFIED", True)
    # 7 연간(PER_year=100) + 1 분기 interim(PER_year=100000). interim 제외 + 최근 5년 상한.
    ratio = [{"period": f"20{y}12", "eps": 100, "bps": None, "roe": None} for y in (19, 20, 21, 22, 23, 24, 25)]
    ratio.append({"period": "202603", "eps": 1, "bps": None, "roe": None})  # 분기 → 제외돼야
    yep = {f"20{y}12": 10000 for y in (19, 20, 21, 22, 23, 24, 25)}  # PER_year=100
    yep["202603"] = 100000  # interim 잘못 포함되면 평균 폭등
    fin = _financials(ratio=ratio, year_end_prices=yep)
    r = build_stock_summary(_valuation(), fin, _valuation(per=100), _chart([]))
    assert r["avg_per"] == pytest.approx(100.0, abs=0.01)  # interim/구연도 제외 → 전부 100
    assert r["sample_years"] == constants.FINANCIALS_LOOKBACK_YEARS  # 창 상한 적용


# ── valuation_label ±10% 경계 (코드가 라벨 확정) ─────────────────────────────

def test_valuation_label_boundaries__valuation_label():
    assert _valuation_label(-10.1) == "저평가"
    assert _valuation_label(-10.0) == "적정"   # 경계 포함
    assert _valuation_label(-9.9) == "적정"
    assert _valuation_label(10.0) == "적정"    # 경계 포함
    assert _valuation_label(10.1) == "고평가"
    assert _valuation_label(None) is None


# ── avg_per 게이트 + 근사 ────────────────────────────────────────────────────

def _avg_per_inputs():
    ratio = [
        {"period": "202112", "eps": 1000, "bps": None, "roe": None},
        {"period": "202212", "eps": 1100, "bps": None, "roe": None},
        {"period": "202312", "eps": 1200, "bps": None, "roe": None},
    ]
    year_end_prices = {"202112": 10000, "202212": 13200, "202312": 14400}
    # PER_year = 10.0, 12.0, 12.0 → mean 11.333
    fin = _financials(ratio=ratio, year_end_prices=year_end_prices)
    val = _valuation(per=15.0, price=15000)
    return fin, val


def test_avg_per_gate_off_returns_none_even_with_data__avg_per_gate(monkeypatch):
    # 게이트 OFF → 데이터가 충분해도 밸류에이션 3필드는 None(안전 폴백). 기본값에 의존하지 않게 명시 설정.
    monkeypatch.setattr(constants, "AVG_PER_VERIFIED", False)
    fin, val = _avg_per_inputs()
    r = build_stock_summary(_valuation(), fin, val, _chart([]))
    assert r["avg_per"] is None
    assert r["per_vs_avg"] is None
    assert r["valuation_label"] is None
    assert r["current_per"] == 15.0  # current_per 는 게이트와 무관하게 산출


def test_avg_per_approximation_when_verified__avg_per_gate(monkeypatch):
    monkeypatch.setattr(constants, "AVG_PER_VERIFIED", True)
    fin, val = _avg_per_inputs()
    r = build_stock_summary(_valuation(), fin, val, _chart([]))
    assert r["avg_per"] == pytest.approx(11.333, abs=0.01)
    assert r["per_vs_avg"] == pytest.approx((15.0 - 11.333) / 11.333 * 100, abs=0.1)
    assert r["valuation_label"] == "고평가"  # +32% > +10
    assert r["sample_years"] == 3


def test_avg_per_excludes_nonpositive_eps_and_missing_price__avg_per_gate(monkeypatch):
    monkeypatch.setattr(constants, "AVG_PER_VERIFIED", True)
    ratio = [
        {"period": "202012", "eps": -50, "bps": None, "roe": None},   # 적자 → 제외
        {"period": "202112", "eps": 1000, "bps": None, "roe": None},  # 종가 결측 → 제외
        {"period": "202212", "eps": 1100, "bps": None, "roe": None},
        {"period": "202312", "eps": 1200, "bps": None, "roe": None},
    ]
    year_end_prices = {"202212": 13200, "202312": 14400}  # 202112 없음
    fin = _financials(ratio=ratio, year_end_prices=year_end_prices)
    r = build_stock_summary(_valuation(), fin, _valuation(per=12.0), _chart([]))
    # 유효 표본 2개(<MIN_HISTORY_YEARS 3) → None
    assert r["avg_per"] is None


# ── RSI (Wilder, 데이터 부족 → None) ─────────────────────────────────────────

def test_rsi_all_gains_is_100__rsi():
    closes = list(range(1, RSI_LEN := constants.RSI_PERIOD + 5))  # 전부 상승
    assert _rsi([float(c) for c in closes], constants.RSI_PERIOD) == pytest.approx(100.0, abs=0.001)


def test_rsi_insufficient_candles_is_none__rsi():
    closes = [float(c) for c in range(constants.RSI_PERIOD)]  # period 개(< period+1)
    assert _rsi(closes, constants.RSI_PERIOD) is None


def test_rsi_in_range_and_sorts_by_date__rsi():
    # 미정렬(내림차순) 캔들도 date 오름차순 정렬 후 계산 — 정렬 안 하면 RSI 가 뒤집힌다.
    closes = [10, 11, 10.5, 12, 11.5, 13, 12.5, 14, 13.5, 15, 14.5, 16, 15.5, 17, 16.5, 18]
    ch = _chart(closes)
    ch["candles"] = list(reversed(ch["candles"]))  # 내림차순으로 뒤집어 입력
    r = build_stock_summary(_valuation(), _financials(), _valuation(price=18), ch)
    assert r["rsi"] is not None and 0.0 <= r["rsi"] <= 100.0
    assert r["rsi"] > 50.0  # 전반적 상승 추세


# ── 이동평균 갭 / 52주 위치 ──────────────────────────────────────────────────

def test_ma20_gap_uses_valuation_price__ma():
    closes = [100.0] * constants.MA_PERIOD  # MA20 = 100
    r = build_stock_summary(_valuation(), _financials(), _valuation(price=110.0), _chart(closes))
    assert r["ma20_gap_pct"] == pytest.approx(10.0, abs=0.01)  # (110-100)/100


def test_ma20_gap_insufficient_is_none__ma():
    closes = [100.0] * (constants.MA_PERIOD - 1)
    r = build_stock_summary(_valuation(), _financials(), _valuation(price=110.0), _chart(closes))
    assert r["ma20_gap_pct"] is None


def test_pos_52w_endpoints_and_clamp__pos52w():
    val_low = _valuation(price=100, week52_high=200, week52_low=100)
    val_high = _valuation(price=200, week52_high=200, week52_low=100)
    val_mid = _valuation(price=150, week52_high=200, week52_low=100)
    val_over = _valuation(price=250, week52_high=200, week52_low=100)
    f, c = _financials(), _chart([])
    assert build_stock_summary(_valuation(), f, val_low, c)["pos_52w_pct"] == pytest.approx(0.0)
    assert build_stock_summary(_valuation(), f, val_high, c)["pos_52w_pct"] == pytest.approx(100.0)
    assert build_stock_summary(_valuation(), f, val_mid, c)["pos_52w_pct"] == pytest.approx(50.0)
    assert build_stock_summary(_valuation(), f, val_over, c)["pos_52w_pct"] == pytest.approx(100.0)


def test_pos_52w_zero_range_is_none__pos52w():
    val = _valuation(price=150, week52_high=150, week52_low=150)  # 분모 0
    r = build_stock_summary(_valuation(), _financials(), val, _chart([]))
    assert r["pos_52w_pct"] is None


# 국면 진입게이트(regime_gate·regime_entry_blocked)는 폐기(항목3) — 관련 테스트 제거.
# 국면은 현금비중만 관리하며 종목별 PER/PBR/편입 커트가 없다(REGIME_PARAMS 는 cash 만).


# ── forward_valuation — 예측 PER = 현재가 ÷ 예측 EPS (KIS 리서치 컨센서스) ────

def _estimate(periods, analyst="김한국", rec="매수", est_date="20260630"):
    return {"analyst": analyst, "est_date": est_date, "recommendation": rec, "periods": periods}


def test_forward_per_computed_from_price_and_est_eps__forward():
    # 삼성 실측: 현재가 304000 / 예측EPS(2027E 64296) ≈ 4.73 (사용자 확인 "4배 정도")
    est = _estimate([
        {"period": "202512", "is_estimate": False, "eps": 6605, "per": 18.2},
        {"period": "202612", "is_estimate": True, "eps": 44362, "per": 6.1},
        {"period": "202712", "is_estimate": True, "eps": 64296, "per": 4.2},
    ])
    r = forward_valuation(est, _valuation(price=304000))
    fpers = {x["period"]: x["forward_per"] for x in r["forward_per"]}
    assert set(fpers) == {"202612", "202712"}  # 추정 연도만(실적연도 제외)
    assert fpers["202712"] == pytest.approx(304000 / 64296, abs=0.05)  # ≈ 4.73
    assert fpers["202612"] == pytest.approx(304000 / 44362, abs=0.05)  # ≈ 6.85


def test_forward_per_carries_consensus_source__forward():
    r = forward_valuation(_estimate([{"period": "202612", "is_estimate": True, "eps": 44362, "per": 6.1}]),
                          _valuation(price=304000))
    assert r["analyst"] == "김한국" and r["recommendation"] == "매수" and r["est_date"] == "20260630"


def test_forward_per_none_on_nonpositive_eps__forward():
    # 손실 예상(EPS<=0)은 예측 PER 계산 불가 → None (억지 계산 금지)
    est = _estimate([{"period": "202612", "is_estimate": True, "eps": -500, "per": None}])
    r = forward_valuation(est, _valuation(price=304000))
    assert r["forward_per"][0]["forward_per"] is None


def test_forward_per_none_on_missing_price__forward():
    est = _estimate([{"period": "202612", "is_estimate": True, "eps": 44362, "per": 6.1}])
    r = forward_valuation(est, _valuation())  # price None
    assert r["forward_per"][0]["forward_per"] is None


def test_forward_valuation_empty_when_uncovered__forward():
    # 리서치 미대상: periods 없음 → forward_per=[] (graceful)
    r = forward_valuation(_estimate([]), _valuation(price=304000))
    assert r["forward_per"] == []
    assert r["prev_year_per"] is None


def test_forward_valuation_prev_year_per__forward():
    # 직전년도(마지막 실적) PER = 현재가 ÷ 직전 실적 EPS (예측과 동일 기준 → 추이 비교 가능)
    est = _estimate([
        {"period": "202412", "is_estimate": False, "eps": 5000, "per": 12.0},
        {"period": "202512", "is_estimate": False, "eps": 6605, "per": 18.2},  # 마지막 실적
        {"period": "202612", "is_estimate": True, "eps": 44362, "per": 6.1},
    ])
    r = forward_valuation(est, _valuation(price=304000))
    assert r["prev_year_period"] == "202512"
    assert r["prev_year_per"] == pytest.approx(304000 / 6605, abs=0.05)  # ≈ 46.0


# ── 안전: LLM 미개입 (소스에 openai/anthropic import 0건) ────────────────────

def test_no_llm_import_in_engine__safety():
    root = Path(__file__).resolve().parents[3]
    for fname in ("stock/summary.py", "stock/constants.py"):
        src = (root / fname).read_text(encoding="utf-8")
        assert "import openai" not in src and "import anthropic" not in src
        assert "from openai" not in src and "from anthropic" not in src
