"""리포트 시스템 프롬프트 안전 서술 — 국면 결측 표면화 + 진입차단/밸류 초과 게이트(IMP-07).

두 LLM 표면(챗봇 build_prompt·리포트 report)의 진입 안전 지침이 갈리지 않게, 리포트도
공유 ENTRY_SIGNAL_RULES 를 쓰고 국면 결측·진입차단을 프롬프트에 표면화한다.
"""
from __future__ import annotations

from chat.build_prompt import ENTRY_SIGNAL_RULES
from chat.report import _build_report_prompt
from macro.engine import REGIME_PARAMS


def _bundle(gate):
    return {
        "ticker": "005930",
        "basic": {"name": "삼성전자"},
        "summary": {"current_per": 12.0, "valuation_label": "적정"},
        "regime_gate": gate,
    }


def _gate(**kw):
    base = {"regime": "수축", "entry_blocked": False, "per_over": False, "pbr_over": False,
            "single_cap": 5, "per_max": 20, "pbr_max": 2.0}
    base.update(kw)
    return base


def test_report_prompt_flags_missing_regime_and_forbids_fabrication():
    # judgement 결측(FRED 실패) → 국면 데이터 없음 명시 + 근거 없는 국면 서술 금지 + 판단 보류.
    prompt = _build_report_prompt(_bundle({}), {})
    assert "국면 데이터" in prompt
    assert "보류" in prompt or "데이터 없음" in prompt
    assert "지어내" in prompt  # 없는 국면·상한 숫자 생성 금지 지시


def test_report_prompt_entry_blocked_emphasis():
    # 과열(entry_blocked) → 종합의견 낙관 금지 + 관찰 대상 서술.
    prompt = _build_report_prompt(
        _bundle(_gate(regime="과열", entry_blocked=True, single_cap=0, per_max=None, pbr_max=None)),
        {"regime": "과열", "recommended_cash_ratio": 80, "params": {}},
    )
    assert "신규 진입" in prompt and ("억제" in prompt or "권하지 않" in prompt)
    assert "관찰" in prompt


def test_report_prompt_valuation_over_emphasis():
    prompt = _build_report_prompt(
        _bundle(_gate(per_over=True)),
        {"regime": "수축", "recommended_cash_ratio": 20, "params": {}},
    )
    assert "상한" in prompt and "초과" in prompt


def test_report_prompt_shares_entry_signal_rules():
    # 챗봇과 동일 진입 서술 규칙(SSOT)을 리포트도 그대로 포함.
    prompt = _build_report_prompt(
        _bundle(_gate()), {"regime": "수축", "recommended_cash_ratio": 20, "params": {}}
    )
    assert ENTRY_SIGNAL_RULES in prompt


def test_report_prompt_entry_rules_have_no_hardcoded_regime_values():
    # 공유 규칙 문구에 REGIME_PARAMS 구체값(per_max 15/20 등) 하드코딩 금지(regime-agnostic).
    for regime, params in REGIME_PARAMS.items():
        for key in ("per_max", "pbr_max"):
            v = params.get(key)
            if v is not None:
                assert str(v) not in ENTRY_SIGNAL_RULES
