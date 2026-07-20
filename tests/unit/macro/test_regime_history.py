"""국면 궤적 빌더 — 과거 월별 지표를 엔진에 재현해 국면 이동 족적을 만든다(순수·결정적).

judge_regime 을 그대로 재사용하므로 라이브 판정과 3중 일관성 자동. 여기선 정렬·부분지표·결측 스킵만 검증.
"""
from __future__ import annotations

from macro.regime_history import build_trajectory, downsample_trajectory, trajectory_step


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


# ── 표본 간격(다운샘플) ──────────────────────────────────────────────────────
def test_trajectory_step_by_range():
    # 1년=분기 · 2년=반기 · 3년=연 (사용자 규칙).
    assert trajectory_step(12) == (3, "quarterly")
    assert trajectory_step(24) == (6, "semiannual")
    assert trajectory_step(36) == (12, "annual")
    # 사이값·상한 일반화(경계 <=).
    assert trajectory_step(6) == (3, "quarterly")
    assert trajectory_step(18) == (6, "semiannual")
    assert trajectory_step(60) == (12, "annual")


def test_downsample_anchors_latest_and_steps_back():
    # 12개월 분기(step 3) → 최근(12월) 앵커에서 3개월씩 뒤로 = 03·06·09·12 (등간격·오름차순).
    pts = [{"date": f"2024-{m:02d}-01"} for m in range(1, 13)]
    out = downsample_trajectory(pts, 3)
    assert [p["date"] for p in out] == ["2024-03-01", "2024-06-01", "2024-09-01", "2024-12-01"]
    assert out[-1] == pts[-1]  # 가장 최근 점 항상 포함(브릿지 연결 보존)


def test_downsample_annual_over_36_months_keeps_three_points():
    # 36개월 연(step 12) → 3점, 최근 포함.
    pts = [{"date": f"{2024 + i // 12}-{i % 12 + 1:02d}-01"} for i in range(36)]
    out = downsample_trajectory(pts, 12)
    assert len(out) == 3
    assert out[-1] == pts[-1]


def test_downsample_noop_when_step1_or_tiny():
    assert downsample_trajectory([], 3) == []
    one = [{"date": "2024-01-01"}]
    assert downsample_trajectory(one, 3) == one
    pair = [{"date": "2024-01-01"}, {"date": "2024-02-01"}]
    assert downsample_trajectory(pair, 3) == pair  # 2점 이하 → 표본화 안 함(월별 유지)
    assert downsample_trajectory(pair, 1) == pair  # step 1 = 원본(월별 그대로)


def test_downsample_guards_against_over_thinning():
    # 창이 step 보다 짧아 표본이 1점으로 과박되면 가장 과거 점을 보강 → 최소 2점(선이 그려지게).
    pts = [{"date": f"2024-{m:02d}-01"} for m in range(1, 4)]  # 3개월
    out = downsample_trajectory(pts, 3)  # 분기 간격 > 창(3개월)
    assert [p["date"] for p in out] == ["2024-01-01", "2024-03-01"]  # 과거+최근 2점
