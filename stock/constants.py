"""종목 정량요약 SSOT 상수 — plan §6.5a, quant-engine-rules §4.

3중 일관성(§1): 이 값들은 여기 한 곳에서만 정의한다.
  코드 상수 → 번들 indicator_config(프론트 차트 지표) → W09 프롬프트 기준표.
같은 숫자를 두 곳에 쓰는 순간 언젠가 어긋난다.

REGIME_PARAMS 는 여기 재정의하지 않는다 — 종목 국면정합성 판정은 macro.engine 의
REGIME_PARAMS 를 import 만 해서 소비한다(역발상 값의 단일 출처는 매크로 엔진).
"""
from __future__ import annotations

# 밸류에이션 판정 밴드(±%). per_vs_avg 가
#   < -10 → 저평가 / > +10 → 고평가 / -10 ~ +10(경계 포함) → 적정.
# 스펙 §6.5a 가 리터럴로 못박은 유일한 정식 3중 일관성 대상.
VALUATION_BAND_PCT = 10

# 이동평균·RSI 기간 — 차트(klinecharts) 지표와 단일 출처(INDICATOR_CONFIG 로 노출).
MA_PERIOD = 20
RSI_PERIOD = 14

# 고지로(小次郎講師) 이동평균선 대순환 — 3 SMA(단기/중기/장기) 기간(일봉 표준 5/20/40).
# 세 선의 상→하 배열 순서로 6단계 국면을 판정하는 결정적 지표. 차트 3MA 오버레이 기간도
# INDICATOR_CONFIG 로 프론트에 내려 SSOT 유지(klinecharts 가 4번째 진실이 되지 않게).
GRAND_CYCLE_MA_PERIODS = (5, 20, 40)   # (단기, 중기, 장기)
GRAND_CYCLE_MIN_CANDLES = 40           # 장기 SMA 미달(< 40봉) → 대순환 None(graceful)
GRAND_CYCLE_TRANSITION_WINDOW = 20     # 밴드 확대/축소 판정 비교 창(봉)

# 6단계 라벨 SSOT(1~6, 배열 상→하). name/arrangement/phase 단일 출처 — 프론트·프롬프트 복제 금지.
# 사이클은 1→2→3→4→5→6→1 순행(인접 두 선 교차로 한 칸씩). 판정은 코드, 서술은 프론트/LLM.
GRAND_CYCLE_STAGES = {
    1: {"name": "안정 상승기", "arrangement": "단 > 중 > 장", "phase": "상승"},
    2: {"name": "상승 둔화기", "arrangement": "중 > 단 > 장", "phase": "상승"},
    3: {"name": "하락 진입기", "arrangement": "중 > 장 > 단", "phase": "전환"},
    4: {"name": "안정 하락기", "arrangement": "장 > 중 > 단", "phase": "하락"},
    5: {"name": "하락 둔화기", "arrangement": "장 > 단 > 중", "phase": "하락"},
    6: {"name": "상승 진입기", "arrangement": "단 > 장 > 중", "phase": "전환"},
}

# CAGR·avg_per 계산 최소 표본 연수. 미달 시 해당 필드 None(신규상장 방어, 임의값 금지).
MIN_HISTORY_YEARS = 3

# CAGR·avg_per 에 쓰는 최근 연간(결산) 표본 상한 — 스펙 §6.5a "5년 평균".
# 라이브 발견: KIS 재무는 종목에 따라 20년 이상 연간 + 최신 분기 interim 을 섞어 준다.
# (a) 최빈 결산월(예 12) 연간만 사용해 분기 interim 을 제외하고,
# (b) 그중 최근 N년만 평균/CAGR 에 쓴다 — 오래된 사업국면(20년 전)이 현재 판단을 흐리지 않게.
FINANCIALS_LOOKBACK_YEARS = 5

# 지표 산출 최소 캔들 수. 미달 시 해당 지표 None.
MIN_CHART_CANDLES_RSI = RSI_PERIOD + 1
MIN_CHART_CANDLES_MA = MA_PERIOD

# 52주 룩백(참고용). 실제 52주 고저는 valuation(inquire_price) 을 권위로 쓰고
# chart 폴백은 결측 시에만 — 이 상수는 폴백 경로에서만 참조.
WEEK_52_TRADING_DAYS = 252

# basic 메타·financials 캐시 TTL(초, §7). 현재가·시세는 캐시 대상이 아니다(원칙1).
STOCK_META_TTL_SECONDS = 6 * 3600

# avg_per(자기 과거평균 PER) 근사의 데이터 기준(EPS/주가 조정기준) 라이브 검증 게이트.
#
# 과거 PER 시계열을 직접 주는 KIS API가 없어, 연도별 EPS × 결산기말 종가로 근사한다.
# 그런데 EPS 와 종가의 조정기준(액면분할 반영 여부)이 어긋나면 "그럴듯하지만 틀린"
# PER 이 나와 valuation_label(저평가/고평가)까지 조용히 오염된다 — 이는 결측(None)보다
# 나쁘다(적대적 검증 critical).
#
# [2026-07-07 라이브 검증 통과 → True] 삼성전자(005930, 2018년 50:1 액면분할)로
# tests/live/test_live_stock_bundle.py 4게이트 확인: (1) 재무 히스토리 23년(표본 충분),
# (2) 연도별 PER_year 가 현재 PER 대비 자릿수 튐 없음(조정기준 일치), (3) real 도메인
# 재무 API 정상, (4) 일봉 100/회. + 분기 interim 혼입 버그를 결산월 연간필터로 제거.
# ⚠ 재검증이 필요한 변경(어댑터 조정기준·소스 교체) 시 다시 False 로 내리고 라이브 확인.
AVG_PER_VERIFIED = True

# 지표 기간을 번들이 프론트(klinecharts)로 내려주는 단일 출처.
# grand_cycle: 대순환 3MA 오버레이 기간 + 6단계 카탈로그(프론트가 6-스텝 라벨을 복제하지 않게).
INDICATOR_CONFIG = {
    "ma_period": MA_PERIOD,
    "rsi_period": RSI_PERIOD,
    "grand_cycle": {
        "periods": {
            "short": GRAND_CYCLE_MA_PERIODS[0],
            "medium": GRAND_CYCLE_MA_PERIODS[1],
            "long": GRAND_CYCLE_MA_PERIODS[2],
        },
        "stages": [
            {"stage": k, "name": v["name"], "arrangement": v["arrangement"], "phase": v["phase"]}
            for k, v in sorted(GRAND_CYCLE_STAGES.items())
        ],
    },
}

# NOTE: RSI 과매수/과매도 라벨(70/30)·52주 고점권/저점권 라벨은 W08 스코프 밖 —
# 스펙 §6.5a 는 rsi 원시값만 반환한다. 도입 시 여기 SSOT 상수 추가 + 사용자 확인.


# ── 재무 100점 점수(스크리너 후보 정량화) — SSOT ─────────────────────────────
# 결정적 코드 점수(LLM/랜덤 0). 4축 균등(각 25점) = 수익성·성장성·안정성·밸류에이션.
# macro _INDICATOR_SPEC/score_axes 패턴 미러링: 임계·배점을 여기 한 곳에서만 정의하고
# stock/financial_score.py 가 이 dict 를 읽어 점수화(함수에 숫자 하드코딩 금지 → 잠금 테스트).
# direction "high"=클수록 우량(value>=threshold → points), "low"=작을수록 우량(value<threshold → points).
# 어느 티어에도 안 걸리면 floor. 값 None → 해당 축 무투표(가용 축으로 재정규화·임의값 금지).
FINANCIAL_SCORE_AXIS_MAX = 25

FINANCIAL_SCORE_SPEC = {
    "roe": {  # 수익성 — 재무비율 roe_val(%)
        "axis": "수익성", "label": "ROE", "unit": "%", "direction": "high",
        "tiers": [(15.0, 25), (10.0, 18), (5.0, 10), (0.0, 4)], "floor": 0,
    },
    "net_income_growth": {  # 성장성 — 순이익증가율 ntin_inrt(%)
        "axis": "성장성", "label": "순이익증가율", "unit": "%", "direction": "high",
        "tiers": [(20.0, 25), (10.0, 18), (0.0, 10)], "floor": 3,
    },
    "debt_ratio": {  # 안정성 — 부채비율 lblt_rate(%, 낮을수록 우량)
        "axis": "안정성", "label": "부채비율", "unit": "%", "direction": "low",
        "tiers": [(50.0, 25), (100.0, 18), (200.0, 10)], "floor": 3,
    },
    "per_vs_avg": {  # 밸류에이션 — 현재 PER vs 자기5년평균(%, 저평가일수록 우량·서빙 라이브 주입)
        "axis": "밸류에이션", "label": "PER vs 자기평균", "unit": "%", "direction": "low",
        "tiers": [(-10.0, 25), (10.0, 15), (50.0, 8)], "floor": 2,
    },
}

# 프론트 노출용 — 반드시 SPEC 파생(4번째 진실 방지). 라벨/축/최대점만.
FINANCIAL_SCORE_CONFIG = {
    "max_score": 100,
    "axis_max": FINANCIAL_SCORE_AXIS_MAX,
    "axes": [
        {"key": k, "axis": v["axis"], "label": v["label"], "unit": v["unit"],
         "direction": v["direction"], "max": FINANCIAL_SCORE_AXIS_MAX}
        for k, v in FINANCIAL_SCORE_SPEC.items()
    ],
}
