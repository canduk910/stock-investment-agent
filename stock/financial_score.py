"""재무 100점 점수 — 결정적 순수 함수(LLM/랜덤 0, macro score_axes 철학).

4축 균등(각 25점): 수익성(ROE)·성장성(순이익증가율)·안정성(부채비율)·밸류에이션(PER vs 자기평균).
임계·배점은 constants.FINANCIAL_SCORE_SPEC 단일 출처(여기 숫자 하드코딩 금지 → 잠금 테스트).

- 수익성/성장성/안정성 = 연간 확정 재무비율(정규화 필드 roe·net_income_growth·debt_ratio).
  최신 연간(최빈 결산월, 분기 interim 제외 — _recent_annual_periods 재사용)만 쓴다.
- 밸류에이션 = per_vs_avg(현재 PER vs 자기5년평균). 스캔 저장분엔 없고 서빙이 라이브 PER 로
  주입할 때만 축에 포함(없으면 3축으로 재정규화).
- 값 None 인 축은 무투표 → 가용 축 합/최대 × 100 으로 재정규화(임의값 금지·None+사유 계약).
  전 축 결측이면 score=None.

판정은 코드(이 점수)이지 매수/매도 판정이 아니다 — 프론트가 정량 지표 요약으로 표시·면책.
"""
from __future__ import annotations

from stock import constants as C
from stock.summary import _recent_annual_periods

# 스캔 저장분(연간 재무)으로 채우는 축 — 밸류에이션은 서빙 라이브 PER 로만.
_ANNUAL_AXES = ("roe", "net_income_growth", "debt_ratio")


def _axis_points(key: str, value):
    """축 값 → 점수(0~AXIS_MAX). SPEC 티어를 읽어 판정(함수에 임계 하드코딩 금지).

    direction "high": value >= threshold 인 첫 티어. "low": value < threshold 인 첫 티어.
    어느 티어에도 안 걸리면 floor. value None → None(무투표).
    """
    spec = C.FINANCIAL_SCORE_SPEC.get(key)
    if spec is None or value is None:
        return None
    high = spec["direction"] == "high"
    for threshold, points in spec["tiers"]:
        if high and value >= threshold:
            return points
        if not high and value < threshold:
            return points
    return spec["floor"]


def _latest_annual_row(ratio: list[dict]) -> dict:
    """최신 연간 재무비율 행(최빈 결산월 연간, 분기 interim 제외). 없으면 {}."""
    if not ratio:
        return {}
    allowed = _recent_annual_periods([r.get("period") for r in ratio])
    annual = [r for r in ratio if str(r.get("period")) in allowed] or list(ratio)
    return max(annual, key=lambda r: str(r.get("period") or ""))


def financial_score(ratio: list[dict], per_vs_avg=None) -> dict:
    """연도별 재무비율(+옵션 per_vs_avg) → 재무 100점.

    반환: {score:int|None, axes:[{key,axis,label,value,points,max}], available_axes:int, note:str|None}.
    per_vs_avg 미주입 시 밸류 축은 제외(스캔 저장 = 3축, 서빙 = 4축).
    """
    latest = _latest_annual_row(ratio)
    values = {
        "roe": latest.get("roe"),
        "net_income_growth": latest.get("net_income_growth"),
        "debt_ratio": latest.get("debt_ratio"),
        "per_vs_avg": per_vs_avg,
    }

    axes = []
    for key, spec in C.FINANCIAL_SCORE_SPEC.items():
        if key == "per_vs_avg" and per_vs_avg is None:
            continue  # 밸류 축은 서빙에서 라이브 PER 주입 시만
        value = values.get(key)
        axes.append({
            "key": key,
            "axis": spec["axis"],
            "label": spec["label"],
            "value": value,
            "points": _axis_points(key, value),
            "max": C.FINANCIAL_SCORE_AXIS_MAX,
        })

    available = [a for a in axes if a["points"] is not None]
    if not available:
        return {"score": None, "axes": axes, "available_axes": 0, "note": "재무 데이터 부족"}

    earned = sum(a["points"] for a in available)
    max_total = sum(a["max"] for a in available)
    score = round(earned / max_total * 100)
    note = "일부 지표 결측 — 가용 축 기준 환산" if len(available) < len(axes) else None
    return {"score": score, "axes": axes, "available_axes": len(available), "note": note}
