"""종목 정량요약 엔진 — plan §6.5a (전부 결정적, LLM 미개입).

매크로 엔진(macro/engine.py)과 같은 철학: 성장성(CAGR)·밸류에이션(자기 과거평균 대비)·
기술적(RSI/이평/52주) 판정 라벨을 **코드가** 확정한다. LLM 호출은 절대 넣지 않는다
(quant-engine-rules §1). 입력 dict → 출력 dict 순수 함수.

## 핵심 아이디어 — 자기 자신과의 비교
"PER 15가 싼가"는 절대 기준이 없지만 "이 종목 과거 평균 대비 -18%"는 근거가 명확하다.
과거 평균 PER 을 직접 주는 KIS API 가 없어 연도별 EPS × 결산기말 종가로 근사하되,
데이터 조정기준(액면분할) 검증 전에는 산출을 보류한다(constants.AVG_PER_VERIFIED 게이트).

## 누락 안전
값이 없으면 임의 기본값(0·평균)으로 채우지 않고 해당 필드 None + notes 에 사유를 남긴다
(macro score_axes 의 `is not None` 가드와 같은 정신). 항상 고정 키를 반환한다.
"""
from __future__ import annotations

from collections import Counter

from stock import constants as C
from macro.engine import REGIME_PARAMS  # noqa: F401  (역발상 값 SSOT — import 소비 확인용)


# ── 숫자·기간 코어스 ─────────────────────────────────────────────────────────

def _num(x):
    """정규화된 숫자(또는 문자열)를 float 로. 부적합/None 은 None(TypeError 금지)."""
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    try:
        return float(str(x).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _year(period):
    """결산년월(stac_yymm, 예 '202312') → 연도 int. 부적합은 None."""
    if not period:
        return None
    s = str(period)
    return int(s[:4]) if len(s) >= 4 and s[:4].isdigit() else None


def _fiscal_month(periods):
    """periods 의 최빈 결산월(MM). 연간 결산월을 추정해 분기 interim(다른 월)을 가려낸다."""
    months = [str(p)[4:6] for p in periods if p and len(str(p)) >= 6]
    if not months:
        return None
    # 최다 빈도, 동률이면 큰 월(최신 결산 관례) 우선.
    return max(Counter(months).items(), key=lambda kv: (kv[1], kv[0]))[0]


def _recent_annual_periods(periods):
    """최빈 결산월 연간만 남기고(분기 interim 제외) 최근 FINANCIALS_LOOKBACK_YEARS 개 반환(set).

    라이브 발견: KIS 재무는 20년+ 연간에 최신 분기 interim(202603 등)을 섞어 준다.
    interim 을 CAGR 종점·avg_per 표본에 쓰면 왜곡되므로 결산월 연간만, 그중 최근 N년만 쓴다.
    """
    fm = _fiscal_month(periods)
    if fm is None:
        return set()
    annual = sorted({str(p) for p in periods if p and str(p)[4:6] == fm}, reverse=True)
    return set(annual[: C.FINANCIALS_LOOKBACK_YEARS])


# ── 성장성: CAGR ─────────────────────────────────────────────────────────────

def _cagr(points):
    """[(year:int, value:float)] → CAGR(%) 또는 None.

    - 표본 < MIN_HISTORY_YEARS → None(신규상장 방어).
    - 기초/기말 <= 0(적자 시작·부호전환) → None(음수 밑 거듭제곱은 미정의, 억지 계산 금지).
    - 연율화 지수는 **실제 연도차**(양끝 연도 차)로, list 길이가 아니다(결측 연도 왜곡 방지).
    """
    pts = sorted((p for p in points if p[0] is not None and p[1] is not None), key=lambda x: x[0])
    if len(pts) < C.MIN_HISTORY_YEARS:
        return None
    first_year, base = pts[0]
    last_year, end = pts[-1]
    span = last_year - first_year
    if span <= 0 or base <= 0 or end <= 0:
        return None
    return ((end / base) ** (1.0 / span) - 1.0) * 100.0


# ── 밸류에이션: 자기 과거평균 PER ────────────────────────────────────────────

def _avg_per(ratio, year_end_prices):
    """연도별 EPS × 결산기말 종가로 PER_year 산출 → 산술평균. (avg_per, sample_years).

    eps<=0 연도·종가 결측/<=0 연도는 제외. 유효 표본 < MIN_HISTORY_YEARS 면 avg_per=None.
    결산기말 종가는 오케스트레이터가 year_end_prices[period] 로 주입(엔진은 fetch 안 함).
    분기 interim 은 제외하고 최근 결산연도(FINANCIALS_LOOKBACK_YEARS)만 쓴다.
    """
    ratio = ratio or []
    allowed = _recent_annual_periods([row.get("period") for row in ratio])
    pers = []
    for row in ratio:
        period = row.get("period")
        eps = _num(row.get("eps"))
        if not period or str(period) not in allowed or eps is None or eps <= 0:
            continue
        price = _num((year_end_prices or {}).get(period))
        if price is None or price <= 0:
            continue
        pers.append(price / eps)
    if len(pers) < C.MIN_HISTORY_YEARS:
        return None, (len(pers) if pers else None)
    return sum(pers) / len(pers), len(pers)


def _valuation_label(per_vs_avg):
    """per_vs_avg(%) → 라벨. ±VALUATION_BAND_PCT 경계는 '적정'(포함). LLM 불가변."""
    if per_vs_avg is None:
        return None
    if per_vs_avg < -C.VALUATION_BAND_PCT:
        return "저평가"
    if per_vs_avg > C.VALUATION_BAND_PCT:
        return "고평가"
    return "적정"


# ── 기술적: RSI / 이동평균 / 52주 위치 ───────────────────────────────────────

def _sorted_closes(chart):
    """chart.candles → date 오름차순 종가 리스트(미정렬 입력도 정렬)."""
    candles = (chart or {}).get("candles") or []
    rows = [(c.get("date"), _num(c.get("close"))) for c in candles]
    rows = [(d, v) for (d, v) in rows if d is not None and v is not None]
    rows.sort(key=lambda x: x[0])
    return [v for (_, v) in rows]


def _rsi(closes, period):
    """Wilder RSI. 캔들 < period+1 → None. 전량 상승→100, 전량 하락→0."""
    if not closes or len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):  # Wilder 평활
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def _ma_gap(closes, price, period):
    """(현재가 - MA) / MA (%). 캔들 < period 또는 현재가 없음 → None. 현재가는 라이브 valuation."""
    if not closes or len(closes) < period or price is None:
        return None
    ma = sum(closes[-period:]) / period
    if ma == 0:
        return None
    return (price - ma) / ma * 100.0


def _pos_52w(price, high, low):
    """52주 밴드 내 위치(0~100% clamp). 분모 0/결측 → None. valuation(inquire_price) 권위."""
    if price is None or high is None or low is None:
        return None
    rng = high - low
    if rng <= 0:
        return None
    return max(0.0, min(100.0, (price - low) / rng * 100.0))


# ── 기술적: 고지로 이동평균선 대순환 (3 SMA 배열 6단계 + 밴드) ────────────────

def _sma(closes, period):
    """말단 단순이동평균(최근 period개 종가 평균). 봉 부족 → None."""
    if not closes or len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def _stage_of(s, m, l):
    """3 SMA(단기 s·중기 m·장기 l) 값 → 대순환 1~6 단계. 결측/동률(경계) → None.

    6단계 = 세 선의 상→하 배열(3! 순열). 동률이면 배열이 미확정이라 None(억지 판정 금지).
    """
    if s is None or m is None or l is None:
        return None
    if s == m or m == l or s == l:
        return None
    if s > m > l:
        return 1  # 안정 상승기(정배열)
    if m > s > l:
        return 2  # 상승 둔화기
    if m > l > s:
        return 3  # 하락 진입기
    if l > m > s:
        return 4  # 안정 하락기(역배열)
    if l > s > m:
        return 5  # 하락 둔화기
    if s > l > m:
        return 6  # 상승 진입기
    return None


def _stage_at(closes, i, periods):
    """closes[..i] 기준 i 번째 봉의 대순환 단계. 장기 SMA 미달 구간이면 None."""
    s_p, m_p, l_p = periods
    if i + 1 < l_p:
        return None
    s = sum(closes[i - s_p + 1: i + 1]) / s_p
    m = sum(closes[i - m_p + 1: i + 1]) / m_p
    l = sum(closes[i - l_p + 1: i + 1]) / l_p
    return _stage_of(s, m, l)


def _ma_grand_cycle(closes):
    """고지로 이동평균선 대순환 — 3 SMA 배열 6단계 + 밴드 + 지속/전환. 결정적, LLM 미개입.

    입력: date 오름차순 종가(_sorted_closes 결과). len < 장기(GRAND_CYCLE_MIN_CANDLES) → None(graceful).
    반환: {stage(1~6/None), stage_name, arrangement, phase, ma{short,medium,long},
           periods{short,medium,long}, band_width_pct, band_direction(확대/축소/유지/None),
           bars_in_stage, prev_stage}.
    band_width_pct = (단기MA − 장기MA)/장기MA×100. 방향은 전환창(N봉) 전 절대폭 대비 증감.
    """
    periods = C.GRAND_CYCLE_MA_PERIODS
    s_p, m_p, l_p = periods
    if not closes or len(closes) < l_p:
        return None

    ma_s, ma_m, ma_l = _sma(closes, s_p), _sma(closes, m_p), _sma(closes, l_p)
    stage = _stage_of(ma_s, ma_m, ma_l)
    meta = C.GRAND_CYCLE_STAGES.get(stage) if stage else None

    band_width = (ma_s - ma_l) / ma_l * 100.0 if ma_l else None

    # 밴드 방향: 전환창 전 절대폭 대비 확대/축소(추세 강화/약화).
    n = len(closes)
    prev_i = n - 1 - C.GRAND_CYCLE_TRANSITION_WINDOW
    band_direction = None
    if band_width is not None and prev_i >= l_p - 1:
        s_prev = sum(closes[prev_i - s_p + 1: prev_i + 1]) / s_p
        l_prev = sum(closes[prev_i - l_p + 1: prev_i + 1]) / l_p
        if l_prev:
            band_prev = (s_prev - l_prev) / l_prev * 100.0
            if abs(band_width) > abs(band_prev):
                band_direction = "확대"
            elif abs(band_width) < abs(band_prev):
                band_direction = "축소"
            else:
                band_direction = "유지"

    # 단계 시계열(장기 계산 가능한 전 구간) → 현재 단계 지속 봉수·직전(전환) 단계.
    stages = [_stage_at(closes, i, periods) for i in range(l_p - 1, n)]
    bars_in_stage = 0
    for st in reversed(stages):
        if st is not None and st == stage:
            bars_in_stage += 1
        else:
            break
    prev_stage = None
    for st in reversed(stages):
        if st is not None and st != stage:
            prev_stage = st
            break

    return {
        "stage": stage,
        "stage_name": meta["name"] if meta else None,
        "arrangement": meta["arrangement"] if meta else None,
        "phase": meta["phase"] if meta else None,
        "ma": {"short": ma_s, "medium": ma_m, "long": ma_l},
        "periods": {"short": s_p, "medium": m_p, "long": l_p},
        "band_width_pct": band_width,
        "band_direction": band_direction,
        "bars_in_stage": bars_in_stage,
        "prev_stage": prev_stage,
    }


# ── 조립 ─────────────────────────────────────────────────────────────────────

def build_stock_summary(basic, financials, valuation, chart):
    """DART/KIS 재무 + KIS 시세에서 결정적 정량요약 산출. LLM 미개입.

    입력(정규화 계약):
      basic: {name, sector, listed_shares, ...}  (메타 전용, 현재가 없음)
      valuation: {price, per, pbr, eps, week52_high, week52_low, ...}  (라이브)
      financials: {income:[{period,revenue,operating_income}], ratio:[{period,eps}],
                   year_end_prices:{period: close}}
      chart: {candles:[{date, close, ...}]}
    반환: 고정 9키 + sample_years + notes. 미산출 필드는 None(키 삭제 아님).
    """
    financials = financials or {}
    valuation = valuation or {}
    notes: list[str] = []

    income = financials.get("income") or []
    ratio = financials.get("ratio") or []
    year_end_prices = financials.get("year_end_prices") or {}

    # 성장성 — 최빈 결산월 연간(분기 interim 제외) 최근 창만 사용
    income_allowed = _recent_annual_periods([r.get("period") for r in income])
    _in_window = [r for r in income if str(r.get("period")) in income_allowed]
    rev_cagr = _cagr([(_year(r.get("period")), _num(r.get("revenue"))) for r in _in_window])
    op_cagr = _cagr([(_year(r.get("period")), _num(r.get("operating_income"))) for r in _in_window])

    # 밸류에이션(자기 과거평균 대비) — AVG_PER_VERIFIED 게이트
    current_per = _num(valuation.get("per"))
    avg_per, sample_years = _avg_per(ratio, year_end_prices)
    if not C.AVG_PER_VERIFIED:
        if avg_per is not None:
            notes.append("avg_per 데이터 기준(EPS/주가 조정) 라이브 검증 전 — 밸류에이션 판정 보류")
        avg_per = None
    if current_per is not None and avg_per not in (None, 0):
        per_vs_avg = (current_per - avg_per) / avg_per * 100.0
    else:
        per_vs_avg = None
    valuation_label = _valuation_label(per_vs_avg)

    # 기술적
    closes = _sorted_closes(chart)
    price = _num(valuation.get("price"))
    rsi = _rsi(closes, C.RSI_PERIOD)
    ma20_gap_pct = _ma_gap(closes, price, C.MA_PERIOD)
    pos_52w_pct = _pos_52w(price, _num(valuation.get("week52_high")), _num(valuation.get("week52_low")))

    # 고지로 이동평균선 대순환(3 SMA 배열 6단계) — 봉 부족 시 None + 사유 note(차트 자체가 없으면 침묵).
    ma_grand_cycle = _ma_grand_cycle(closes)
    if ma_grand_cycle is None and closes:
        notes.append(
            f"대순환: 최근 거래일 {len(closes)}봉으로 장기 {C.GRAND_CYCLE_MIN_CANDLES}봉 미달 — 대순환 보류"
        )

    return {
        "rev_cagr": rev_cagr,
        "op_cagr": op_cagr,
        "current_per": current_per,
        "avg_per": avg_per,
        "per_vs_avg": per_vs_avg,
        "valuation_label": valuation_label,
        "rsi": rsi,
        "ma20_gap_pct": ma20_gap_pct,
        "pos_52w_pct": pos_52w_pct,
        "ma_grand_cycle": ma_grand_cycle,
        "sample_years": sample_years,
        "notes": notes,
    }


def forward_valuation(estimate, valuation):
    """예측 PER = 현재가 ÷ 예측 EPS (KIS 리서치 컨센서스 기반). 코드가 계산, LLM 미개입.

    후행 PER(현재가/과거 EPS)의 한계 — 주가가 실적을 선반영하면 과대 — 를 보완한다.
    예: 삼성 현재 PER 46 이지만 시장은 실적 폭증(AI/메모리)을 전망 → 2027E 예측 PER≈4.7.
    실적 폭증 전망이 정당한 고평가/저평가 판단인지 판정하지 않고, 컨센서스 숫자만 투명하게 전달
    (출처 애널리스트·기준일 동반). EPS<=0(손실 예상)·현재가 결측 → 해당 forward_per None.
    """
    estimate = estimate or {}
    valuation = valuation or {}
    price = _num(valuation.get("price"))
    periods = estimate.get("periods") or []

    def _per_at_price(eps):
        return price / eps if (price is not None and eps is not None and eps > 0) else None

    forward = []
    for period in periods:
        if not period.get("is_estimate"):
            continue  # 실적 연도는 제외 — 예측만
        forward.append({
            "period": period.get("period"),
            "eps": _num(period.get("eps")),
            "forward_per": _per_at_price(_num(period.get("eps"))),
            "kis_per": _num(period.get("per")),  # KIS 저장 예측 PER(추정시점가 기준) — 교차참고
        })

    # 직전년도 PER — 마지막 확정 실적연도 EPS 로 현재가 기준 PER(예측과 동일 기준 → 추이 비교 가능).
    actuals = sorted(
        (p for p in periods if not p.get("is_estimate")),
        key=lambda p: str(p.get("period") or ""),
    )
    prev = actuals[-1] if actuals else None

    return {
        "forward_per": forward,
        "prev_year_per": _per_at_price(_num(prev.get("eps"))) if prev else None,
        "prev_year_period": prev.get("period") if prev else None,
        "analyst": estimate.get("analyst"),
        "est_date": estimate.get("est_date"),
        "recommendation": estimate.get("recommendation"),
    }


# 국면별 종목 진입게이트(regime_gate·regime_entry_blocked)는 "너무 보수적"이라 폐기(항목3).
# 국면은 현금비중만 관리한다 — 종목별 PER/PBR/편입 커트·진입차단·국면정합성 판정은 없다.
