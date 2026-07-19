"""국면 궤적 빌더 — 과거 월별 지표를 엔진에 재현해 국면 이동 족적을 만든다(순수·결정적).

judge_regime 을 그대로 재사용하므로 라이브 판정과 3중 일관성 자동. 여기선 정렬·부분지표·결측 스킵만 검증.
"""
from __future__ import annotations

from macro.regime_history import build_trajectory


def _series(*pairs):
    """[(date, value), ...] → [{date, value}, ...]."""
    return [{"date": d, "value": v} for d, v in pairs]


def test_two_months_full_indicators_reconstruct_regime():
    # 1월: 전지표 양호/탐욕 → cs=+2, ss=+2 → "확장". 2월: 전지표 악화/공포 → cs=-2, ss=-2 → "수축".
    traj = build_trajectory(
        {
            "yield_spread": _series(("2024-01-01", 0.6), ("2024-02-01", -0.2)),
            "hy_spread": _series(("2024-01-01", 2.5), ("2024-02-01", 6.0)),
            "vix": _series(("2024-01-01", 12.0), ("2024-02-01", 30.0)),
            "fear_greed": _series(("2024-01-01", 80.0), ("2024-02-01", 20.0)),
        }
    )
    assert len(traj) == 2
    jan, feb = traj
    assert jan["date"] == "2024-01-01"
    assert (jan["cycle_score"], jan["sentiment_score"], jan["regime"]) == (2, 2, "확장")
    assert jan["recommended_cash_ratio"] == 60
    assert (feb["cycle_score"], feb["sentiment_score"], feb["regime"]) == (-2, -2, "수축")
    assert feb["recommended_cash_ratio"] == 20


def test_ascending_order_even_if_input_unsorted():
    # 양축(경기 yield + 심리 vix)을 채워 축 규칙 통과, 입력 정렬과 무관하게 시간 오름차순 반환.
    traj = build_trajectory(
        {
            "yield_spread": _series(("2024-03-01", 0.6), ("2024-01-01", 0.6), ("2024-02-01", 0.6)),
            "vix": _series(("2024-03-01", 30.0), ("2024-01-01", 12.0), ("2024-02-01", 20.0)),
        }
    )
    assert [p["date"] for p in traj] == ["2024-01-01", "2024-02-01", "2024-03-01"]


def test_fear_greed_missing_sentiment_from_vix_alone():
    # 공포탐욕지수 시계열이 없어도(CNN 결측) 심리축은 VIX 단독으로 판정된다 — 궤적 유지.
    traj = build_trajectory(
        {
            "yield_spread": _series(("2024-01-01", 0.6)),
            "hy_spread": _series(("2024-01-01", 2.5)),
            "vix": _series(("2024-01-01", 12.0)),  # <14 → 심리 +1
        }
    )
    assert len(traj) == 1
    p = traj[0]
    assert p["cycle_score"] == 2 and p["sentiment_score"] == 1  # vix 단독
    assert p["regime"] == "확장"
    assert "fear_greed" in p["missing_indicators"]


def test_partial_but_both_axes_present_is_plotted():
    # 각 축에 지표 1개씩만 있어도(경기=yield, 심리=vix) 두 축이 다 있으면 플롯된다.
    traj = build_trajectory(
        {"yield_spread": _series(("2024-01-01", 0.6)), "vix": _series(("2024-01-01", 30.0))}
    )
    assert len(traj) == 1
    p = traj[0]
    assert p["cycle_score"] == 1 and p["sentiment_score"] == -1  # yield>0.5 +1, vix>28 -1


def test_month_missing_an_axis_is_skipped():
    # 심리축만 있고 경기축 지표가 전무한 달(대표: FRED 월 집계 전 당월 — fear_greed 만) → 스킵.
    #   그 축 점수가 데이터 부족 탓에 0(중앙)으로 강제되는 아티팩트 방지.
    traj = build_trajectory(
        {
            "yield_spread": _series(("2024-01-01", 0.6), ("2024-02-01", 0.6)),
            "vix": _series(("2024-01-01", 12.0), ("2024-02-01", 12.0)),
            "fear_greed": _series(("2024-01-01", 50.0), ("2024-02-01", 50.0), ("2024-03-01", 55.0)),
        }
    )
    # 3월은 fear_greed(심리)만 → 경기축 결측 → 스킵. 1·2월은 양축 다 있음.
    assert [p["date"] for p in traj] == ["2024-01-01", "2024-02-01"]


def test_none_values_are_excluded():
    # present-but-None 값은 엔진에 안 넘어간다(누락 처리). 양축은 채워 축 규칙과 분리해 검증.
    traj = build_trajectory(
        {
            "yield_spread": _series(("2024-01-01", 0.6)),
            "hy_spread": _series(("2024-01-01", 2.5)),
            "vix": [{"date": "2024-01-01", "value": None}],  # None → 제외
            "fear_greed": _series(("2024-01-01", 80.0)),
        }
    )
    assert len(traj) == 1
    p = traj[0]
    # vix None 제외 → 심리는 fear_greed(80>75)만 +1. 경기 yield+hy 둘 다 양호 → +2.
    assert p["cycle_score"] == 2 and p["sentiment_score"] == 1
    assert "vix" in p["missing_indicators"]


def test_empty_or_single_axis_returns_empty():
    assert build_trajectory({}) == []
    assert build_trajectory({"vix": []}) == []
    # 심리만(경기축 전무) → 스킵 → 빈 궤적.
    assert build_trajectory({"vix": _series(("2024-01-01", 12.0))}) == []


def test_exclude_month_drops_in_progress_month():
    # 진행 중 당월(부분 데이터)은 결정적으로 제외 — 양축이 다 있어도(부분월 평균) 빠진다.
    series = {
        "yield_spread": _series(("2024-01-01", 0.6), ("2024-02-01", 0.6)),
        "vix": _series(("2024-01-01", 12.0), ("2024-02-01", 30.0)),
    }
    assert [p["date"] for p in build_trajectory(series, exclude_month="2024-02")] == ["2024-01-01"]
    # exclude 없으면 둘 다 포함(기본 동작 불변).
    assert len(build_trajectory(series)) == 2


def test_vix_panic_flag_carried_per_month():
    # 양축을 채워 축 규칙 통과(경기 yield). vix_panic 플래그가 달마다 실려 온다.
    traj = build_trajectory(
        {
            "yield_spread": _series(("2024-01-01", 0.6), ("2024-02-01", 0.6)),
            "vix": _series(("2024-01-01", 40.0), ("2024-02-01", 12.0)),
        }
    )
    assert traj[0]["vix_panic"] is True  # 40 > 35
    assert traj[1]["vix_panic"] is False
