"""매크로 2축 국면 판정 엔진 경계·분류 테스트 — plan §4·§6.1 (TDD Red 단계).

2축 설계: 경기(cycle = 신용·금리) 축과 심리(sentiment = 변동성·심리) 축을 각각
독립 점수화(-2..+2)한 뒤 2×2 매트릭스(9셀)로 국면을 결정한다. 판정은 전부 결정적
코드(LLM 미개입). 이 목록이 곧 스펙이다(tdd-workflow §정량 엔진) — 각 테스트 이름
접미사(__cycle_axis/__sentiment_axis/__classify/__confidence/__vix_panic/
__contrarian_cash/__single_source/__missing/__2axis)로 스펙 근거를 추적한다.

절대 규칙(tdd-workflow): 테스트가 실패하면 구현을 고친다. 임계값 경계상수를 테스트에
맞춰 바꾸지 않는다. recommended_cash_ratio 는 REGIME_PARAMS 단일 출처(별도 CASH_RATIO
상수 금지).
"""
from __future__ import annotations

import macro.engine as engine
from macro.engine import (
    REGIME_PARAMS,
    VIX_PANIC,
    classify,
    judge_regime,
    score_axes,
)

# 경기/심리 축 부호를 만드는 재사용 데이터 조각(다른 축은 중립값으로 고정).
_CYCLE_양호 = {"yield_spread": 0.51, "hy_spread": 4.0}   # cs=+1 (금리차 정상)
_CYCLE_중립 = {"yield_spread": 0.2, "hy_spread": 4.0}    # cs=0
_CYCLE_악화 = {"yield_spread": -0.1, "hy_spread": 4.0}   # cs=-1 (금리차 역전)
_SENT_공포 = {"vix": 28.1, "fear_greed": 50}             # ss=-1 (변동성 급등)
_SENT_중립 = {"vix": 20, "fear_greed": 50}               # ss=0
_SENT_탐욕 = {"vix": 13.9, "fear_greed": 50}             # ss=+1 (변동성 안정)


def _cell(cycle: dict, sent: dict) -> dict:
    return {**cycle, **sent}


# ── 경기 축 점수 경계 (yield_spread >0.5→+1 / <0→-1, hy_spread <3.0→+1 / >5.0→-1) ──

def test_cycle_yield_neg0_1_score_minus1__cycle_axis():
    r = score_axes({"yield_spread": -0.1})
    assert r["cycle_score"] == -1
    assert ("장단기 금리차 역전", "경기", "악화") in r["drivers"]


def test_cycle_yield_0_no_vote__cycle_axis():
    assert score_axes({"yield_spread": 0})["cycle_score"] == 0


def test_cycle_yield_0_5_no_vote__cycle_axis():
    # 0.5 는 정상 상단 경계 — > 0.5 엄격이라 무투표
    assert score_axes({"yield_spread": 0.5})["cycle_score"] == 0


def test_cycle_yield_0_51_score_plus1__cycle_axis():
    r = score_axes({"yield_spread": 0.51})
    assert r["cycle_score"] == 1
    assert ("장단기 금리차 정상", "경기", "양호") in r["drivers"]


def test_cycle_hy_5_1_score_minus1__cycle_axis():
    r = score_axes({"hy_spread": 5.1})
    assert r["cycle_score"] == -1
    assert ("신용스프레드 확대", "경기", "악화") in r["drivers"]


def test_cycle_hy_5_0_no_vote__cycle_axis():
    # 5.0 은 정상 상단 경계(3.0~5.0 inclusive) — 무투표
    assert score_axes({"hy_spread": 5.0})["cycle_score"] == 0


def test_cycle_hy_3_0_no_vote__cycle_axis():
    assert score_axes({"hy_spread": 3.0})["cycle_score"] == 0


def test_cycle_hy_2_9_score_plus1__cycle_axis():
    r = score_axes({"hy_spread": 2.9})
    assert r["cycle_score"] == 1
    assert ("신용스프레드 안정", "경기", "양호") in r["drivers"]


# ── 심리 축 점수 경계 (vix <14→+1 / >28→-1, fear_greed >75→+1 / <25→-1) ──────────

def test_sentiment_vix_28_no_vote__sentiment_axis():
    assert score_axes({"vix": 28})["sentiment_score"] == 0


def test_sentiment_vix_28_1_score_minus1__sentiment_axis():
    r = score_axes({"vix": 28.1})
    assert r["sentiment_score"] == -1
    assert ("변동성 급등", "심리", "공포") in r["drivers"]


def test_sentiment_vix_14_no_vote__sentiment_axis():
    assert score_axes({"vix": 14})["sentiment_score"] == 0


def test_sentiment_vix_13_9_score_plus1__sentiment_axis():
    r = score_axes({"vix": 13.9})
    assert r["sentiment_score"] == 1
    assert ("변동성 안정", "심리", "탐욕") in r["drivers"]


def test_sentiment_fg_25_no_vote__sentiment_axis():
    assert score_axes({"fear_greed": 25})["sentiment_score"] == 0


def test_sentiment_fg_24_9_score_minus1__sentiment_axis():
    r = score_axes({"fear_greed": 24.9})
    assert r["sentiment_score"] == -1
    assert ("극단적 공포", "심리", "공포") in r["drivers"]


def test_sentiment_fg_75_no_vote__sentiment_axis():
    assert score_axes({"fear_greed": 75})["sentiment_score"] == 0


def test_sentiment_fg_75_1_score_plus1__sentiment_axis():
    r = score_axes({"fear_greed": 75.1})
    assert r["sentiment_score"] == 1
    assert ("극단적 탐욕", "심리", "탐욕") in r["drivers"]


# ── 축 합산 (두 지표가 같은 방향이면 누적, 반대면 상쇄) ────────────────────────────

def test_cycle_both_악화_score_minus2__cycle_axis():
    # yield -0.1 (-1) + hy 5.1 (-1) → cs=-2
    assert score_axes({"yield_spread": -0.1, "hy_spread": 5.1})["cycle_score"] == -2


def test_cycle_one_양호_one_악화_score_0_중립__cycle_axis():
    # yield 0.51 (+1) + hy 5.1 (-1) → cs=0 (중립)
    assert score_axes({"yield_spread": 0.51, "hy_spread": 5.1})["cycle_score"] == 0


# ── 9셀 분류 전부 (classify(cs, ss)) ─────────────────────────────────────────────

def test_classify_양호_공포_회복__classify():
    assert classify(1, -1) == "회복"


def test_classify_양호_중립_확장__classify():
    assert classify(1, 0) == "확장"


def test_classify_양호_탐욕_확장__classify():
    assert classify(1, 1) == "확장"


def test_classify_중립_공포_회복__classify():
    assert classify(0, -1) == "회복"


def test_classify_중립_중립_확장__classify():
    assert classify(0, 0) == "확장"


def test_classify_중립_탐욕_과열__classify():
    assert classify(0, 1) == "과열"


def test_classify_악화_공포_수축__classify():
    assert classify(-1, -1) == "수축"


def test_classify_악화_중립_수축__classify():
    assert classify(-1, 0) == "수축"


def test_classify_악화_탐욕_과열__classify():
    assert classify(-1, 1) == "과열"


# ── 발산 케이스: 심리는 같은 탐욕이어도 경기 부호가 다르면 국면이 갈린다 ──────────────

def test_divergence_악화탐욕_과열_vs_양호탐욕_확장__classify():
    bad = judge_regime(_cell(_CYCLE_악화, _SENT_탐욕))
    good = judge_regime(_cell(_CYCLE_양호, _SENT_탐욕))
    assert bad["regime"] == "과열"    # 매크로 부러짐 + 심리 좋음 = 위험 고점
    assert good["regime"] == "확장"   # 건강한 확장
    assert bad["regime"] != good["regime"]


# ── judge_regime 이 classify 결과를 그대로 국면으로 쓰는지(9셀 통합) ────────────────

def test_judge_regime_uses_classify_for_all_cells__2axis():
    cases = [
        (_CYCLE_양호, _SENT_공포, "회복"),
        (_CYCLE_양호, _SENT_중립, "확장"),
        (_CYCLE_양호, _SENT_탐욕, "확장"),
        (_CYCLE_중립, _SENT_공포, "회복"),
        (_CYCLE_중립, _SENT_중립, "확장"),
        (_CYCLE_중립, _SENT_탐욕, "과열"),
        (_CYCLE_악화, _SENT_공포, "수축"),
        (_CYCLE_악화, _SENT_중립, "수축"),
        (_CYCLE_악화, _SENT_탐욕, "과열"),
    ]
    for cycle, sent, regime in cases:
        assert judge_regime(_cell(cycle, sent))["regime"] == regime


# ── 축 부호 라벨 (cycle: 양호/중립/악화, sentiment: 탐욕/중립/공포) ───────────────────

def test_axes_sign_labels__2axis():
    r = judge_regime(_cell(_CYCLE_악화, _SENT_탐욕))  # cs=-1, ss=+1 → 과열
    assert r["axes"]["cycle"]["score"] == -1
    assert r["axes"]["cycle"]["sign"] == "악화"
    assert r["axes"]["sentiment"]["score"] == 1
    assert r["axes"]["sentiment"]["sign"] == "탐욕"
    assert r["regime"] == "과열"


# ── 신뢰도 = 두 축 신호 유무 (둘 다≠0 high / 한 축만≠0 medium / 둘 다0 low) ──────────

def test_confidence_both_axes_signal_high__confidence():
    # cs=+1(yield 0.51), ss=-1(vix 28.1) → high
    assert judge_regime({"yield_spread": 0.51, "vix": 28.1})["confidence"] == "high"


def test_confidence_one_axis_signal_medium__confidence():
    # cs=+1, ss 신호 없음 → medium
    assert judge_regime({"yield_spread": 0.51})["confidence"] == "medium"


def test_confidence_all_zero_확장_low__confidence():
    # 지표는 있으나 전부 중립 구간 → 두 축 0 → 확장 + low
    r = judge_regime(_cell(_CYCLE_중립, _SENT_중립))
    assert r["regime"] == "확장"
    assert r["confidence"] == "low"


# ── vix_panic: 블랭킷 오버라이드 아님, 플래그만 (vix>35 True, 35 False) ──────────────

def test_vix_panic_40_true_and_sentiment_공포__vix_panic():
    r = judge_regime({"vix": 40})
    assert r["vix_panic"] is True
    assert r["axes"]["sentiment"]["sign"] == "공포"  # vix 40 > 28 → 심리 공포


def test_vix_panic_is_flag_not_regime_override__vix_panic():
    # vix=40 단독: 경기 중립·심리 공포 → classify(0,-1)=회복. 오버라이드였다면 수축이었을 것.
    r = judge_regime({"vix": 40})
    assert r["vix_panic"] is True
    assert r["regime"] == "회복"


def test_vix_panic_35_false_boundary__vix_panic():
    # 35 은 VIX_PANIC(35) 초과 아님(> 엄격) → 플래그 False
    assert judge_regime({"vix": 35})["vix_panic"] is False


# ── 역발상 현금비중: 과열80/확장60/회복40/수축20 (REGIME_PARAMS 단일 출처) ───────────

def test_contrarian_cash_과열_80__contrarian_cash():
    # 과열(고평가·탐욕) → 현금 최대. (중립,탐욕)
    r = judge_regime(_cell(_CYCLE_중립, _SENT_탐욕))
    assert r["regime"] == "과열"
    assert r["recommended_cash_ratio"] == 80 == REGIME_PARAMS["과열"]["cash"]


def test_contrarian_cash_수축_20__contrarian_cash():
    # 수축(급락·공포) → 현금 최소(적극 매수). (악화,공포)
    r = judge_regime(_cell(_CYCLE_악화, _SENT_공포))
    assert r["regime"] == "수축"
    assert r["recommended_cash_ratio"] == 20 == REGIME_PARAMS["수축"]["cash"]


def test_contrarian_cash_회복_40__contrarian_cash():
    # 회복. (양호,공포)
    r = judge_regime(_cell(_CYCLE_양호, _SENT_공포))
    assert r["regime"] == "회복"
    assert r["recommended_cash_ratio"] == 40 == REGIME_PARAMS["회복"]["cash"]


def test_contrarian_cash_확장_60__contrarian_cash():
    # 확장. (양호,중립)
    r = judge_regime(_cell(_CYCLE_양호, _SENT_중립))
    assert r["regime"] == "확장"
    assert r["recommended_cash_ratio"] == 60 == REGIME_PARAMS["확장"]["cash"]


# ── 단일 출처 불변식: CASH_RATIO 상수 부재 + cash 3중 일치 ──────────────────────────

def test_no_cash_ratio_constant__single_source():
    assert not hasattr(engine, "CASH_RATIO")


def test_recommended_cash_ratio_triple_consistency__single_source():
    cases = [
        (_cell(_CYCLE_중립, _SENT_탐욕), "과열"),
        (_cell(_CYCLE_악화, _SENT_공포), "수축"),
        (_cell(_CYCLE_양호, _SENT_공포), "회복"),
        (_cell(_CYCLE_양호, _SENT_중립), "확장"),
    ]
    for data, regime in cases:
        r = judge_regime(data)
        assert r["regime"] == regime
        assert (
            r["recommended_cash_ratio"]
            == REGIME_PARAMS[regime]["cash"]
            == r["params"]["cash"]
        )


# ── 누락 지표: present 만 점수 + missing_indicators 기록, all-missing → 확장/low ──────

def test_missing_partial_present_only_scored_records_missing__missing():
    # yield_spread(경기-1), vix(심리-1) 만 존재 → hy_spread, fear_greed 누락
    r = judge_regime({"yield_spread": -0.1, "vix": 28.1})
    assert r["axes"]["cycle"]["score"] == -1
    assert r["axes"]["sentiment"]["score"] == -1
    assert set(r["missing_indicators"]) == {"hy_spread", "fear_greed"}


def test_all_missing_empty_data_확장_low_missing_4__missing():
    r = judge_regime({})
    assert r["regime"] == "확장"
    assert r["confidence"] == "low"
    assert len(r["missing_indicators"]) == 4
    assert set(r["missing_indicators"]) == {
        "yield_spread",
        "hy_spread",
        "vix",
        "fear_greed",
    }


def test_score_axes_missing_keys_no_keyerror__missing():
    # 빈 dict 접근에서 KeyError 나지 않고 0/0 반환
    r = score_axes({})
    assert r["cycle_score"] == 0
    assert r["sentiment_score"] == 0
    assert r["drivers"] == []


# ── 반환 계약: 정확한 키 집합 + votes/override 제거 확인 ──────────────────────────────

def test_judge_regime_return_contract_keys__2axis():
    r = judge_regime({"yield_spread": -0.1, "vix": 28.1})
    assert set(r.keys()) == {
        "regime",
        "recommended_cash_ratio",
        "confidence",
        "axes",
        "key_drivers",
        "params",
        "vix_panic",
        "missing_indicators",
        "raw_data",
    }
    # votes/override 키는 폐기됐다
    assert "votes" not in r
    assert "override" not in r


def test_axes_contract_shape_and_types__2axis():
    r = judge_regime({"yield_spread": -0.1, "vix": 28.1})
    axes = r["axes"]
    assert set(axes.keys()) == {"cycle", "sentiment"}
    for name in ("cycle", "sentiment"):
        assert set(axes[name].keys()) == {"score", "sign"}
        assert isinstance(axes[name]["score"], int)
        assert isinstance(axes[name]["sign"], str)


def test_key_drivers_are_axis_direction_tuples__2axis():
    r = judge_regime({"yield_spread": -0.1, "vix": 28.1})
    assert ("장단기 금리차 역전", "경기", "악화") in r["key_drivers"]
    assert ("변동성 급등", "심리", "공포") in r["key_drivers"]
    for label, axis, direction in r["key_drivers"]:
        assert axis in ("경기", "심리")
        assert direction in ("양호", "악화", "탐욕", "공포")


def test_raw_data_passthrough__2axis():
    data = {"yield_spread": -0.1, "vix": 28.1}
    assert judge_regime(data)["raw_data"] == data


# ── previous_regime: 시그니처만 유지, 판정에 미사용(2축 깜빡임 감쇠는 P2 dormant) ──────

def test_previous_regime_ignored_dormant_p2__2axis():
    data = _cell(_CYCLE_악화, _SENT_탐욕)  # → 과열
    base = judge_regime(data)
    with_prev = judge_regime(data, previous_regime="수축")
    assert base["regime"] == with_prev["regime"] == "과열"


# ── VIX_PANIC 상수 값 고정(플래그 임계) ──────────────────────────────────────────────

def test_vix_panic_constant_is_35__vix_panic():
    assert VIX_PANIC == 35


def test_present_but_none_treated_as_missing__2axis():
    """present-but-None(예: {"vix": None})은 TypeError 없이 누락으로 처리된다.

    (API 경로는 None을 걸러내지만, 엔진 순수함수 자체의 견고성을 고정한다.)
    """
    from macro.engine import judge_regime, score_axes

    # score_axes: None 값이 있어도 크래시 없이 건너뛴다.
    r = score_axes({"yield_spread": None, "hy_spread": 2.0, "vix": None, "fear_greed": 85})
    assert r["cycle_score"] == 1  # hy_spread<3.0 양호만 반영
    assert r["sentiment_score"] == 1  # fear_greed>75 탐욕만 반영

    # judge_regime: None 값 키는 missing_indicators로 잡히고, vix_panic도 안전.
    j = judge_regime({"yield_spread": None, "hy_spread": None, "vix": None, "fear_greed": None})
    assert set(j["missing_indicators"]) == {"yield_spread", "hy_spread", "vix", "fear_greed"}
    assert j["vix_panic"] is False
    assert j["regime"] == "확장"  # 전부 중립 → 확장
    assert j["confidence"] == "low"
