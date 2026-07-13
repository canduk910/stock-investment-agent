"""리포트 시스템 프롬프트 — 국면 결측 표면화 + **국면명·권장 현금비중 제시 → 최종 적합성 판단**.

항목3: 국면 진입게이트(PER/PBR 상한·편입비중 커트) 폐기. 리포트는 국면·현금비중 스탠스 대비
'최종 국면 적합성'을 LLM 에게 판단시킨다(게이트 초과/차단 판정 없음).
"""
from __future__ import annotations

from chat.report import _build_report_prompt


def _bundle():
    return {
        "ticker": "005930",
        "basic": {"name": "삼성전자"},
        "summary": {"current_per": 12.0, "valuation_label": "적정"},
    }


def test_report_prompt_flags_missing_regime_and_forbids_fabrication():
    # judgement 결측(FRED 실패) → 국면 데이터 없음 명시 + 판단 보류 + 근거 없는 숫자 생성 금지.
    prompt = _build_report_prompt(_bundle(), {})
    assert "국면 데이터" in prompt
    assert "보류" in prompt or "데이터 없음" in prompt
    assert "지어내" in prompt


def test_report_prompt_presents_regime_and_cash_for_final_fitness():
    # 국면명 + 권장 현금비중을 제시하고 '최종 적합성'을 판단하도록 요청(사용자 결정).
    prompt = _build_report_prompt(_bundle(), {"regime": "확장", "recommended_cash_ratio": 60})
    assert "확장" in prompt and "60%" in prompt
    assert "현금비중" in prompt and "최종 적합성" in prompt


def test_report_prompt_has_no_entry_gate_cuts():
    # 국면 커트(PER/PBR 상한 초과·진입 차단·종목당 상한)로 판정하지 않음 — 게이트 키 미노출.
    prompt = _build_report_prompt(_bundle(), {"regime": "과열", "recommended_cash_ratio": 80})
    assert "커트는 없다" in prompt  # 국면은 현금비중만 관리
    assert "single_cap" not in prompt and "entry_blocked" not in prompt and "per_over" not in prompt
