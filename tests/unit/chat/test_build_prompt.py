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


def test_prompt_regime_params_are_cash_only():
    # 국면 파라미터는 **현금비중만**(항목3 — single_cap/per_max/pbr_max 폐기).
    text = build_prompt(_JUDGEMENT)
    params = _JUDGEMENT["params"]
    assert str(params["cash"]) in text  # 현금비중 값이 인용 근거로 주입
    assert set(params.keys()) == {"cash"}  # cash 외 국면 커트 파라미터 없음


def test_prompt_reflects_regime_change_on_reinjection():
    # judgement 를 매 호출 주입 → 다른 국면이면 다른 현금비중이 프롬프트에 반영.
    su = judge_regime({"yield_spread": 0.6, "hy_spread": 2.0, "vix": 30.0})  # 회복
    text = build_prompt(su)
    assert str(su["recommended_cash_ratio"]) in text
    assert su["regime"] in text


# ── 국면 = 현금비중만 (항목3) — 종목별 진입게이트(single_cap/per_max/pbr_max) 폐기 ────

# 과열: 현금비중 높음(방어) / 회복: 현금비중 낮음(적극) — 국면별 현금비중 파생만 남는다.
_OVERHEAT = judge_regime(
    {"yield_spread": -0.2, "hy_spread": 6.0, "vix": 40.0, "fear_greed": 80}
)  # 과열
_RECOVERY = judge_regime(
    {"yield_spread": 0.6, "hy_spread": 2.0, "vix": 30.0}
)  # 회복


def test_prompt_manages_cash_ratio_only__no_entry_gate_cuts():
    # 국면은 현금비중만 관리한다는 규칙이 명시되고, 종목별 진입게이트 커트 판정은 하지 않는다.
    text = build_prompt(_OVERHEAT)
    assert "현금비중만" in text  # 국면 = 현금비중만 관리
    assert "진입을 판정하지 않는다" in text  # PER/PBR 상한·편입비중 커트 없음
    assert "참고 데이터" in text  # 개별 종목 PER/PBR 은 참고용


def test_prompt_regime_param_block_is_regime_agnostic__cash_only():
    # 과열/회복 두 국면 모두 '현금비중만' 규칙 문구는 동일(값만 다름) — 커트 문구 하드코딩 없음.
    overheat = build_prompt(_OVERHEAT)
    recovery = build_prompt(_RECOVERY)
    assert "현금비중만" in overheat and "현금비중만" in recovery
    # 폐기된 게이트 변수명이 어느 국면 프롬프트에도 등장하지 않는다.
    for stale in ("per_max", "pbr_max", "entry_blocked", "per_over", "pbr_over"):
        assert stale not in overheat and stale not in recovery


# ── 잔고(포트폴리오) 팝업 규칙 (UX3) — 판정·조언은 텍스트, 데이터는 코드 ────────────


def test_prompt_has_show_balance_rule_in_popup_block():
    # ⑦ 팝업 규칙에 "계좌 잔고/포트폴리오 현황 → show_balance" 안내가 존재.
    text = build_prompt(_JUDGEMENT)
    assert "show_balance" in text
    assert "잔고" in text


def test_prompt_says_rebalance_advice_is_text_only():
    # 리밸런싱·분산 조언은 팝업 없이 텍스트로만(데이터는 프론트가 조회) — 명령형/자동주문 금지.
    text = build_prompt(_JUDGEMENT)
    assert "리밸런싱" in text


# ── 포트폴리오 상담 활성 + 안전 강화(재분류 backstop) ────────────────────────────


def test_prompt_has_portfolio_consultation_block():
    # 코드 근거 자문 블록: 잔고 근거 조정 방향 + 추가편입 후보(국면·분산 관점) + 새 아이디어 + 면책.
    text = build_prompt(_JUDGEMENT)
    assert "포트폴리오 상담" in text
    assert "추가편입" in text
    assert "현금비중" in text  # 국면 권장 현금비중 근거(진입게이트 커트 아님)


def test_prompt_consultation_keeps_no_certainty_and_disclaimer():
    # 완화해도 단정 금지·면책은 유지(불변 안전).
    text = build_prompt(_JUDGEMENT)
    assert "단정" in text
    assert "면허" in text  # 면허 있는 자문 아님(면책)


def test_prompt_safety_refuses_insider_and_manipulation():
    # 재분류 backstop — 본 프롬프트도 내부정보·시세조종·수익보장 단정을 명시적으로 거부.
    text = build_prompt(_JUDGEMENT)
    assert "내부" in text and "시세조종" in text
    assert "보장" in text  # 수익 보장 금지 명시


def test_prompt_allows_actionable_recommendation():
    # 완화의 핵심: 후보를 구체적으로 제시(actionable) 허용 문구가 있어야 한다.
    text = build_prompt(_JUDGEMENT)
    assert "후보" in text  # 편입 검토 후보 제시
