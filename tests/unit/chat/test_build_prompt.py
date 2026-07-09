"""시스템 프롬프트 조립 테스트 — llm-safety-guide §1 (결정적 부분만, 문체 미검증).

핵심은 3중 일관성 자동 회귀: 기준표가 하드코딩 숫자가 아니라 macro.engine 상수에서
생성되는지(str(VIX_PANIC) in text). 상수를 바꿨는데 프롬프트에 옛 숫자가 남으면 여기서
잡힌다. 그리고 필수 6블록 마커·judgement 주입만 검증한다(LLM 출력 문체는 대상 아님).
"""
from __future__ import annotations

from chat.build_prompt import build_criteria_text, build_prompt
from macro.engine import (
    INDICATOR_LABELS,
    THRESHOLDS,
    VIX_PANIC,
    judge_regime,
)

# 실제 엔진 판정 하나(과열: 경기 악화 + 심리 탐욕) — 주입 검증에 사용.
_JUDGEMENT = judge_regime(
    {"yield_spread": -0.2, "hy_spread": 6.0, "vix": 40.0, "fear_greed": 80}
)


# ── build_criteria_text: 상수 유래(하드코딩 금지, 3중 일관성) ──────────────────


def test_criteria_text_includes_vix_panic_constant__triple_consistency():
    # 프롬프트에 VIX_PANIC 숫자를 타이핑하지 않고 상수에서 생성 → 값이 텍스트에 존재.
    assert str(VIX_PANIC) in build_criteria_text()


def test_criteria_text_includes_all_indicator_labels():
    text = build_criteria_text()
    for label in INDICATOR_LABELS.values():
        assert label in text


def test_criteria_text_includes_threshold_boundary_strings():
    # 각 지표 임계 구간 표기(THRESHOLDS 값)가 그대로 포함 — 하드코딩 아님을 고정.
    text = build_criteria_text()
    for key in INDICATOR_LABELS:
        for boundary in THRESHOLDS[key].values():
            assert boundary in text


def test_criteria_text_has_no_hardcoded_stale_number():
    # 회귀 방어: VIX_PANIC 을 바꾸면 옛 숫자가 남지 않아야 한다(이 테스트가 그 계약).
    text = build_criteria_text()
    assert f"> {VIX_PANIC}" in text  # 패닉 오버라이드 라인이 상수로 생성됨


# ── build_prompt: 필수 6블록 + judgement 주입 ────────────────────────────────


def test_prompt_contains_all_six_required_blocks():
    text = build_prompt(_JUDGEMENT)
    # ① 역할(자동매매/자문 아님) ② 판정 출처 고정 ③ 기준표 ④ REGIME_PARAMS
    # ⑤ 설명지침 ⑥ 팝업 규칙 — 마커로 존재 확인.
    assert "국면 판정 출처 고정" in text
    assert "자동매매" in text
    assert "면허" in text  # 면허 있는 자문 아님
    assert "국면 판정 기준" in text  # 기준표 헤더(build_criteria_text)
    assert "단정" in text  # 단정 표현 금지 지침
    assert "손실" in text  # 손실 위험 환기
    assert "팝업" in text or "도구" in text  # 팝업 도구 규칙


def test_prompt_injects_judgement_regime_and_cash_ratio():
    text = build_prompt(_JUDGEMENT)
    assert _JUDGEMENT["regime"] in text  # "과열"
    assert str(_JUDGEMENT["recommended_cash_ratio"]) in text  # 80


def test_prompt_injects_confidence_and_vix_panic_flag():
    text = build_prompt(_JUDGEMENT)
    assert _JUDGEMENT["confidence"] in text
    # vix_panic=True 인 판정이므로 패닉 경보가 프롬프트에 반영.
    assert "패닉" in text


def test_prompt_injects_regime_params_for_current_regime():
    text = build_prompt(_JUDGEMENT)
    params = _JUDGEMENT["params"]
    # per_max 등 국면 파라미터가 인용 근거로 주입(None 이 아닌 값은 문자열로 존재).
    assert str(params["single_cap"]) in text


def test_prompt_reflects_regime_change_on_reinjection():
    # judgement 를 매 호출 주입 → 다른 국면이면 다른 현금비중이 프롬프트에 반영.
    su = judge_regime({"yield_spread": 0.6, "hy_spread": 2.0, "vix": 30.0})  # 회복
    text = build_prompt(su)
    assert str(su["recommended_cash_ratio"]) in text
    assert su["regime"] in text
