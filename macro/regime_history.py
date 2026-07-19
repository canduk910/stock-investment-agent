"""국면 이동 궤적(족적) 빌더 — 과거 월별 지표를 판정 엔진에 재현한다.

`judge_regime` 이 순수·결정적(LLM·네트워크·시간 의존 0)이라, 과거 월별 지표 스냅샷을 그대로 다시
먹이면 그 달의 국면을 **재현**할 수 있다 → 경기×심리 매트릭스 위 월별 궤적. 라이브 판정과 **동일 함수**를
쓰므로 3중 일관성(임계값·현금비중)이 자동으로 유지된다. 이 모듈은 순수(수집·I/O 없음) — 라우트가 수집한
월 시계열을 넘겨받아 정렬·정합·판정만 한다.
"""
from __future__ import annotations

from macro.engine import INDICATOR_KEYS, judge_regime

# 축별 지표 — 매트릭스 점은 경기(세로)·심리(가로) 두 좌표를 다 가져야 의미가 있다.
_CYCLE_KEYS = ("yield_spread", "hy_spread")
_SENTIMENT_KEYS = ("vix", "fear_greed")


def build_trajectory(
    series_by_engine_key: dict[str, list[dict]], exclude_month: str | None = None
) -> list[dict]:
    """엔진키별 월 시계열 → 월별 국면 판정 궤적(시간 오름차순).

    입력: `{engine_key: [{date, value}, ...]}` — engine_key ∈ INDICATOR_KEYS(없는 키=부재).
    각 포인트의 `date` 는 `YYYY-MM-...`(월 키 = `date[:7]`). present-but-None 값은 제외.

    두 가지 가드로 "부분 데이터의 달"을 배제한다:
    1. **진행 중 당월 제외**(`exclude_month`, `YYYY-MM`): FRED 는 `frequency=m` 로 **진행 중 당월도
       '경과일 평균'을 부분 관측치로** 낼 수 있어, 그 달이 확정 과거값처럼 궤적의 '현재' 점이 되고 캐시될
       위험이 있다. 라우트가 오늘(KST) 월을 넘겨 **결정적으로** 배제한다(FRED 의 당월 반환 여부와 무관).
    2. **양축 결측 스킵**: 경기·심리 두 축 모두 지표가 있어야 플롯한다 — 한 축이라도 없으면 그 축 점수가
       데이터 부족 탓에 0(중앙)으로 강제되는 아티팩트가 된다(과거 결측 달 방어).

    각 달마다 값 있는 지표만 담은 dict 를 `judge_regime` 에 넘긴다(부분 지표 안전 — 엔진 가드가 처리).
    반환 원소:
    `{date, cycle_score, sentiment_score, regime, recommended_cash_ratio, vix_panic, missing_indicators}`.
    """
    # 월 키(YYYY-MM) → {engine_key: value}. 값이 있는 지표만 채워진다.
    by_month: dict[str, dict] = {}
    for engine_key in INDICATOR_KEYS:  # 엔진 키 순서로만 수용(예상 밖 키 무시)
        for point in series_by_engine_key.get(engine_key) or []:
            date = point.get("date")
            value = point.get("value")
            if date is None or value is None:
                continue
            month = str(date)[:7]  # YYYY-MM
            by_month.setdefault(month, {})[engine_key] = value

    trajectory: list[dict] = []
    for month in sorted(by_month):  # 시간 오름차순(입력 정렬 무관)
        if exclude_month and month == exclude_month:
            continue  # 진행 중 당월(부분 데이터) 결정적 제외 — FRED 부분월 평균 여부와 무관
        month_data = by_month[month]
        has_cycle = any(k in month_data for k in _CYCLE_KEYS)
        has_sentiment = any(k in month_data for k in _SENTIMENT_KEYS)
        if not (has_cycle and has_sentiment):  # 한 축이라도 결측 → 축 기본값 아티팩트 방지 스킵
            continue
        j = judge_regime(month_data)
        trajectory.append(
            {
                "date": f"{month}-01",  # 월초로 정규화(수집기 형식과 일치)
                "cycle_score": j["axes"]["cycle"]["score"],
                "sentiment_score": j["axes"]["sentiment"]["score"],
                "regime": j["regime"],
                "recommended_cash_ratio": j["recommended_cash_ratio"],
                "vix_panic": j["vix_panic"],
                "missing_indicators": j["missing_indicators"],
            }
        )
    return trajectory
