"""재무 100점 점수 엔진 계약 테스트 — 결정적(LLM/랜덤 0)·경계 Red-first.

4축(수익성 ROE·성장성 순이익증가율·안정성 부채비율·밸류에이션 PER vs 자기평균)을
FINANCIAL_SCORE_SPEC 임계로 점수화 → 가용 축 재정규화로 0~100. macro score_axes 철학
(누락은 무투표, 임의값 금지)과 stock.summary(None+사유) 계약을 미러링한다.
"""
from __future__ import annotations

from stock import constants as C
from stock.financial_score import financial_score, _axis_points


def _ratio(period="202512", **kw):
    base = {"period": period, "eps": 6564.0, "bps": 63997.0,
            "roe": None, "net_income_growth": None, "debt_ratio": None,
            "revenue_growth": None, "op_income_growth": None, "reserve_ratio": None}
    base.update(kw)
    return base


# --- 축 점수(SPEC 경계 잠금) -------------------------------------------------

def test_axis_points_roe_tiers():
    assert _axis_points("roe", 20) == 25   # ≥15
    assert _axis_points("roe", 15) == 25   # 경계 포함(≥)
    assert _axis_points("roe", 14.99) == 18
    assert _axis_points("roe", 10) == 18
    assert _axis_points("roe", 7) == 10
    assert _axis_points("roe", 2) == 4
    assert _axis_points("roe", -1) == 0
    assert _axis_points("roe", None) is None


def test_axis_points_debt_ratio_lower_better():
    assert _axis_points("debt_ratio", 30) == 25    # <50
    assert _axis_points("debt_ratio", 50) == 18    # 경계 아님(<50 실패)
    assert _axis_points("debt_ratio", 120) == 10
    assert _axis_points("debt_ratio", 250) == 3    # floor
    assert _axis_points("debt_ratio", None) is None


def test_axis_points_valuation_lower_better():
    assert _axis_points("per_vs_avg", -20) == 25   # <-10 저평가
    assert _axis_points("per_vs_avg", -10) == 15    # 경계 아님
    assert _axis_points("per_vs_avg", 5) == 15
    assert _axis_points("per_vs_avg", 30) == 8
    assert _axis_points("per_vs_avg", 80) == 2


# --- 종합 점수 -------------------------------------------------------------

def test_all_four_axes_max_is_100():
    r = financial_score([_ratio(roe=20, net_income_growth=30, debt_ratio=30)], per_vs_avg=-20)
    assert r["available_axes"] == 4
    assert r["score"] == 100
    assert r["note"] is None


def test_three_axes_no_valuation_renormalizes_over_75():
    # per_vs_avg 미주입(스캔 저장분) → 3축 기준 재정규화
    r = financial_score([_ratio(roe=10, net_income_growth=10, debt_ratio=50)])  # 18+18+18=54 / 75
    assert r["available_axes"] == 3
    assert r["score"] == round(54 / 75 * 100)  # 72
    assert all(a["key"] != "per_vs_avg" for a in r["axes"])


def test_missing_axis_value_renormalizes_over_available():
    # debt_ratio 결측 → 가용 2축(roe·growth)으로 환산 + 사유 노트
    r = financial_score([_ratio(roe=20, net_income_growth=20)])  # 25+25=50 / 50
    assert r["available_axes"] == 2
    assert r["score"] == 100
    assert r["note"]  # 일부 결측 환산 사유


def test_all_none_returns_none_score():
    r = financial_score([_ratio()])
    assert r["score"] is None
    assert r["available_axes"] == 0
    assert r["note"]


def test_empty_ratio_graceful():
    r = financial_score([])
    assert r["score"] is None


def test_interim_period_excluded_uses_latest_annual():
    # KIS 가 최신 분기 interim(202603)을 섞어줘도 최빈 결산월 연간(202512)을 쓴다.
    rows = [
        _ratio(period="202603", roe=99, net_income_growth=99, debt_ratio=1),  # interim(제외 대상)
        _ratio(period="202512", roe=10, net_income_growth=10, debt_ratio=50),
        _ratio(period="202412", roe=9, net_income_growth=5, debt_ratio=55),
        _ratio(period="202312", roe=4, net_income_growth=-70, debt_ratio=25),
    ]
    r = financial_score(rows)
    roe_axis = next(a for a in r["axes"] if a["key"] == "roe")
    assert roe_axis["value"] == 10  # 202512(연간)의 ROE, interim 99 아님


# --- SSOT: CONFIG 는 SPEC 파생 ----------------------------------------------

def test_config_derived_from_spec():
    cfg = C.FINANCIAL_SCORE_CONFIG
    assert cfg["max_score"] == 100
    spec_keys = set(C.FINANCIAL_SCORE_SPEC.keys())
    cfg_keys = {a["key"] for a in cfg["axes"]}
    assert cfg_keys == spec_keys
    for a in cfg["axes"]:
        assert a["max"] == C.FINANCIAL_SCORE_AXIS_MAX
        assert a["axis"] == C.FINANCIAL_SCORE_SPEC[a["key"]]["axis"]


def test_spec_axis_max_matches_top_tier():
    # 각 축 최고 티어 점수 == AXIS_MAX (재정규화 분모 정합)
    for key, spec in C.FINANCIAL_SCORE_SPEC.items():
        top = max(p for _, p in spec["tiers"])
        assert top == C.FINANCIAL_SCORE_AXIS_MAX
