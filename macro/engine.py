"""매크로 2축 국면 판정 엔진 — plan §4·§6.1 (전부 결정적, LLM 미개입).

이 계층의 모든 산출(국면·현금비중·신뢰도·기여지표)은 규칙 코드가 계산한다.
LLM 호출은 절대 넣지 않는다(quant-engine-rules §1). 입력 dict → 출력 dict 순수 함수.

## 2축 설계
단일축 가중투표를 폐기하고 서로 독립인 두 축으로 국면을 본다.
- 경기(cycle) 축 = 신용·금리(yield_spread, hy_spread): 실물·유동성이 건강한가.
- 심리(sentiment) 축 = 변동성·심리(vix, fear_greed): 시장 심리가 탐욕/공포인가.
각 축을 -2..+2 로 점수화한 뒤 부호(양호/중립/악화 · 탐욕/중립/공포)를 2×2(9셀)
매트릭스에 넣어 국면을 결정한다. 두 축을 분리하면 "매크로가 부러졌는데 심리는 탐욕"
같은 발산(→ 위험한 고점=과열)과 "매크로 건강 + 심리 탐욕"(→ 건강한 확장)을 구분할 수
있다. 단일 가중투표로는 이 둘이 평균으로 섞여 사라진다.

## 3중 일관성(§1): 임계값·파라미터는 이 파일 상수 1곳에서만 정의한다.
- recommended_cash_ratio 는 REGIME_PARAMS[regime]["cash"] 에서만 나온다.
  별도 CASH_RATIO 상수를 만들지 않는다(관점 혼선·불일치 방지).
- THRESHOLDS 는 score_axes 로직과 정확히 1:1 일치한다(score 가 원본, 표기는 파생).

## 판정 순서 (judge_regime)
  1. missing 분리(누락 지표는 점수에서 제외, 임의 기본값 금지)
  2. vix_panic 플래그 계산(블랭킷 오버라이드 아님 — 표시·경보용 플래그만)
  3. score_axes → cycle_score, sentiment_score
  4. classify(cs, ss) → regime
  5. confidence = 두 축 신호 유무(둘 다 high / 한 축 medium / 둘 다 low)
  6. previous_regime 은 시그니처만 유지, 미사용(깜빡임 감쇠는 P2, dormant)
"""
from __future__ import annotations

# VIX 패닉 플래그 임계 — 오버라이드가 아니라 표시용 플래그(2축 판정은 별도).
VIX_PANIC = 35

# 판정 대상 4지표(누락 판정·부분실패 기록의 기준 집합).
INDICATOR_KEYS = ("yield_spread", "hy_spread", "vix", "fear_greed")
# 엔진키 → 한글 라벨 단일 출처(W09 프롬프트 기준표·UI 표기용). INDICATOR_KEYS 와
# 키·순서 1:1(경기축 → 심리축). build_criteria_text()가 이걸 import(3중 일관성).
INDICATOR_LABELS = {
    "yield_spread": "장단기 금리차",
    "hy_spread": "HY 신용스프레드",
    "vix": "VIX 변동성",
    "fear_greed": "공포탐욕지수",
}
# 경기(신용·금리) 축 지표.
CYCLE_KEYS = ("yield_spread", "hy_spread")
# 심리(변동성·심리) 축 지표.
SENTIMENT_KEYS = ("vix", "fear_greed")

# 국면별 실행 파라미터 — "현금비중(%)" 관점 단일 출처(recommended_cash_ratio 의 유일 출처).
# 역발상 배분: 과열(고평가·탐욕)일수록 현금을 늘리고, 수축(급락·공포)일수록 현금을 줄여
# 적극 매수한다. single_cap=0(과열)은 "신규 진입 제안 자체 안 함" 게이트.
REGIME_PARAMS = {
    "회복": {"cash": 40, "single_cap": 4, "per_max": 15, "pbr_max": 1.5},
    "확장": {"cash": 60, "single_cap": 3, "per_max": 15, "pbr_max": 1.5},
    "과열": {"cash": 80, "single_cap": 0, "per_max": None, "pbr_max": None},
    "수축": {"cash": 20, "single_cap": 5, "per_max": 20, "pbr_max": 2.0},
}

# 지표별 구간 표기 — score_axes 와 정확히 1:1 일치(리뷰어·W09 프롬프트 기준표용).
# 경계값(0/0.5, 5.0/3.0, 28/14, 25/75)은 전부 "중립"(무투표). 부등호 그대로.
THRESHOLDS = {
    "yield_spread": {"악화": "< 0", "양호": "> 0.5", "중립": "0 ~ 0.5"},
    "hy_spread": {"악화": "> 5.0", "양호": "< 3.0", "중립": "3.0 ~ 5.0"},
    "vix": {"공포": "> 28", "탐욕": "< 14", "중립": "14 ~ 28"},
    "fear_greed": {"공포": "< 25", "탐욕": "> 75", "중립": "25 ~ 75"},
}


def score_axes(data: dict) -> dict:
    """지표 dict → 경기·심리 두 축 점수와 기여 드라이버.

    각 지표는 `data.get(key) is not None` 가드로만 접근한다 — 키 부재(KeyError)와
    present-but-None(예: {"vix": None}) 둘 다 안전하게 건너뛴다(TypeError 금지).
    경계값은 THRESHOLDS 부등호 그대로 무투표(중립).

    반환: {"cycle_score": int, "sentiment_score": int,
           "drivers": [(label, axis, direction), ...]}
      - axis ∈ {"경기","심리"}, direction ∈ {"양호","악화","탐욕","공포"}
    """
    cycle_score = 0
    sentiment_score = 0
    drivers: list[tuple[str, str, str]] = []

    # ── 경기(cycle) 축: 신용·금리 ──────────────────────────────────────────────
    if data.get("yield_spread") is not None:
        v = data["yield_spread"]
        if v > 0.5:
            cycle_score += 1
            drivers.append(("장단기 금리차 정상", "경기", "양호"))
        elif v < 0:
            cycle_score -= 1
            drivers.append(("장단기 금리차 역전", "경기", "악화"))

    if data.get("hy_spread") is not None:
        v = data["hy_spread"]
        if v < 3.0:
            cycle_score += 1
            drivers.append(("신용스프레드 안정", "경기", "양호"))
        elif v > 5.0:
            cycle_score -= 1
            drivers.append(("신용스프레드 확대", "경기", "악화"))

    # ── 심리(sentiment) 축: 변동성·심리 ────────────────────────────────────────
    if data.get("vix") is not None:
        v = data["vix"]
        if v < 14:
            sentiment_score += 1
            drivers.append(("변동성 안정", "심리", "탐욕"))
        elif v > 28:
            sentiment_score -= 1
            drivers.append(("변동성 급등", "심리", "공포"))

    if data.get("fear_greed") is not None:
        v = data["fear_greed"]
        if v > 75:
            sentiment_score += 1
            drivers.append(("극단적 탐욕", "심리", "탐욕"))
        elif v < 25:
            sentiment_score -= 1
            drivers.append(("극단적 공포", "심리", "공포"))

    return {
        "cycle_score": cycle_score,
        "sentiment_score": sentiment_score,
        "drivers": drivers,
    }


def classify(cs: int, ss: int) -> str:
    """(경기 점수 cs, 심리 점수 ss) → 국면 (2×2, 9셀).

    핵심 발산 규칙: 경기가 악화인데 심리가 탐욕이면 "과열"(위험한 고점)이고,
    경기가 양호하면서 심리가 탐욕이면 "확장"(건강)이다 — 심리만 보면 구분 불가.
    """
    if cs > 0:  # 경기 양호
        return "회복" if ss < 0 else "확장"
    if cs == 0:  # 경기 중립
        if ss < 0:
            return "회복"
        if ss > 0:
            return "과열"
        return "확장"
    # cs < 0: 경기 악화
    return "과열" if ss > 0 else "수축"


def _cycle_sign(cs: int) -> str:
    return "양호" if cs > 0 else ("악화" if cs < 0 else "중립")


def _sentiment_sign(ss: int) -> str:
    return "탐욕" if ss > 0 else ("공포" if ss < 0 else "중립")


def _result(
    regime: str,
    cycle_score: int,
    sentiment_score: int,
    confidence: str,
    drivers: list,
    vix_panic: bool,
    missing: list[str],
    data: dict,
) -> dict:
    """반환 계약 조립 — recommended_cash_ratio·params 는 항상 regime 에서 파생(단일 출처)."""
    return {
        "regime": regime,
        "recommended_cash_ratio": REGIME_PARAMS[regime]["cash"],  # 단일 출처
        "confidence": confidence,
        "axes": {
            "cycle": {"score": cycle_score, "sign": _cycle_sign(cycle_score)},
            "sentiment": {
                "score": sentiment_score,
                "sign": _sentiment_sign(sentiment_score),
            },
        },
        "key_drivers": drivers,  # [(label, axis, direction), ...]
        "params": REGIME_PARAMS[regime],
        "vix_panic": vix_panic,
        "missing_indicators": missing,
        "raw_data": data,
    }


def judge_regime(data: dict, previous_regime: str | None = None) -> dict:
    """4지표 dict → 2축 국면 판정 dict.

    previous_regime 은 시그니처만 유지하고 판정에는 쓰지 않는다 — 2축 경계 깜빡임
    감쇠(하이스테리시스)는 P2 로 미룬 dormant 파라미터다.
    """
    # 1. 누락 지표 분리(점수에서 제외, 임의 기본값 금지). present-but-None 도 누락으로 본다.
    missing = [k for k in INDICATOR_KEYS if data.get(k) is None]

    # 2. vix_panic 플래그 — 블랭킷 오버라이드가 아니라 표시·경보 플래그(> 엄격, 35 미발동).
    vix_panic = data.get("vix") is not None and data["vix"] > VIX_PANIC

    # 3. 두 축 점수화.
    scored = score_axes(data)
    cs = scored["cycle_score"]
    ss = scored["sentiment_score"]

    # 4. 9셀 분류.
    regime = classify(cs, ss)

    # 5. 신뢰도 = 두 축 신호 유무.
    if cs != 0 and ss != 0:
        confidence = "high"
    elif cs != 0 or ss != 0:
        confidence = "medium"
    else:
        confidence = "low"

    return _result(regime, cs, ss, confidence, scored["drivers"], vix_panic, missing, data)
