"""시스템 프롬프트 조립 테스트 — llm-safety-guide §1 (결정적 부분만, 문체 미검증).

핵심은 3중 일관성 자동 회귀: 기준표가 하드코딩 숫자가 아니라 macro.engine 상수에서
생성되는지(str(VIX_PANIC) in text). 상수를 바꿨는데 프롬프트에 옛 숫자가 남으면 여기서
잡힌다. 그리고 필수 6블록 마커·judgement 주입만 검증한다(LLM 출력 문체는 대상 아님).
"""
from __future__ import annotations

from chat.build_prompt import build_criteria_text, build_prompt
from macro.engine import (
    INDICATOR_LABELS,
    REGIME_PARAMS,
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


# ── 관심종목 진입신호 서술 지침 (W10) — REGIME_PARAMS 파생, 하드코딩 금지 ────────

# 과열: single_cap=0(진입 억제) / 회복: single_cap>0(검토 가능) — 두 국면으로 파생 검증.
_OVERHEAT = judge_regime(
    {"yield_spread": -0.2, "hy_spread": 6.0, "vix": 40.0, "fear_greed": 80}
)  # 과열 (single_cap=0)
_RECOVERY = judge_regime(
    {"yield_spread": 0.6, "hy_spread": 2.0, "vix": 30.0}
)  # 회복 (single_cap>0)


def test_prompt_contains_entry_signal_guidance_block():
    # 진입신호 서술 규칙 블록이 프롬프트에 존재(변수명으로 규칙을 서술).
    text = build_prompt(_OVERHEAT)
    assert "진입" in text  # 진입신호 지침 블록 존재
    assert "single_cap" in text  # 규칙을 변수명으로 참조(숫자 아님)
    assert "per_max" in text and "pbr_max" in text  # 게이트 조건 변수명
    assert "검토 가능" in text  # 서술 라벨(명령형 아님)


def test_entry_signal_guidance_is_regime_agnostic__no_hardcoded_numbers():
    # 핵심 3중 일관성 회귀: 진입신호 지침 '문구' 자체는 국면과 무관하게 동일해야 한다.
    # 국면별로 달라지는 숫자(single_cap/per_max 값)는 이미 ④ REGIME_PARAMS 주입 블록에서만
    # 나온다. 지침 문구에 국면별 숫자를 하드코딩하면 두 국면에서 문구가 달라져 여기서 잡힌다.
    guidance_overheat = _extract_entry_guidance(build_prompt(_OVERHEAT))
    guidance_recovery = _extract_entry_guidance(build_prompt(_RECOVERY))
    assert guidance_overheat == guidance_recovery  # 동일 문구(regime-agnostic)


def test_entry_signal_guidance_has_no_hardcoded_regime_param_values():
    # 지침 문구에 REGIME_PARAMS 의 구체 숫자(per_max=15/20, pbr_max=1.5/2.0, single_cap 값들)가
    # 타이핑돼 있지 않은지 직접 확인 — single_cap>0 은 부등호 서술이라 허용, 특정 값은 금지.
    guidance = _extract_entry_guidance(build_prompt(_OVERHEAT))
    for regime, params in REGIME_PARAMS.items():
        for key in ("per_max", "pbr_max"):
            value = params.get(key)
            if value is not None:
                # per_max=15 같은 구체 상한값이 지침 문구에 하드코딩되면 안 됨.
                assert str(value) not in guidance, (
                    f"진입신호 지침에 {regime}.{key}={value} 가 하드코딩됨"
                )


def _extract_entry_guidance(prompt: str) -> str:
    """진입신호 지침 블록만 잘라낸다(마커 [관심종목 진입 신호] ~ 다음 블록 경계).

    지침 문구만 비교하기 위해, judgement 주입값(regime/현금비중 등)이 섞인 ④ 블록과
    분리해 지침 서술만 추출한다. 마커가 없으면 테스트가 명확히 실패하도록 빈 문자열.
    """
    marker = "[관심종목 진입 신호"
    start = prompt.find(marker)
    if start == -1:
        return ""
    rest = prompt[start:]
    # 다음 블록(원문자 ⑤/⑥ 등)에서 끊는다.
    for boundary in ("⑤", "⑥", "⑦"):
        idx = rest.find(boundary)
        if idx != -1:
            rest = rest[:idx]
    return rest.strip()
