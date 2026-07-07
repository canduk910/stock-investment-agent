// 개발/렌더 확인용 샘플 번들 — GET /api/detail/{ticker}/bundle 계약(계획 "번들 계약")을 그대로 따른다.
// 백엔드 미연결(dev) 시 StockReport 가 이 fixture 로 폴백해 UI 를 항상 데모할 수 있게 한다.
// 실 연동은 통합 단계에서 fetchStockBundle 이 대체한다. 수치는 예시(실데이터 아님).

// 결정적 의사난수(LCG) — 매 빌드 동일한 캔들을 생성해 스냅샷/시연이 흔들리지 않게 한다.
function makeRng(seed) {
  let s = seed >>> 0
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0
    return s / 0xffffffff
  }
}

// 최근 약 6개월(주말 제외)의 일봉을 생성한다. klinecharts MA(20)/RSI(14) 표본이 충분하도록 ~130행.
function makeCandles(endDate, count, startPrice, seed) {
  const rng = makeRng(seed)
  const dates = []
  const d = new Date(endDate)
  while (dates.length < count) {
    const day = d.getUTCDay()
    if (day !== 0 && day !== 6) {
      const y = d.getUTCFullYear()
      const m = String(d.getUTCMonth() + 1).padStart(2, '0')
      const dd = String(d.getUTCDate()).padStart(2, '0')
      dates.push(`${y}${m}${dd}`)
    }
    d.setUTCDate(d.getUTCDate() - 1)
  }
  dates.reverse()

  const candles = []
  let prevClose = startPrice
  for (const date of dates) {
    const drift = (rng() - 0.48) * 0.028 // 약한 상승 편향
    const open = Math.round(prevClose * (1 + (rng() - 0.5) * 0.006))
    const close = Math.max(1000, Math.round(open * (1 + drift)))
    const high = Math.round(Math.max(open, close) * (1 + rng() * 0.012))
    const low = Math.round(Math.min(open, close) * (1 - rng() * 0.012))
    const volume = Math.round(8_000_000 + rng() * 14_000_000)
    candles.push({ date, open, high, low, close, volume })
    prevClose = close
  }
  return candles
}

const CANDLES = makeCandles(Date.UTC(2026, 6, 3), 130, 68000, 20260703)
const last = CANDLES[CANDLES.length - 1]
const prev = CANDLES[CANDLES.length - 2]
const highs = CANDLES.map((c) => c.high)
const lows = CANDLES.map((c) => c.low)
const week52High = Math.max(...highs)
const week52Low = Math.min(...lows)
const price = last.close
const changeRate = Number((((price - prev.close) / prev.close) * 100).toFixed(2))

export const sampleBundle = {
  ticker: '005930',
  basic: {
    name: '삼성전자',
    sector: '반도체',
    listed_shares: 5_969_782_550,
  },
  valuation: {
    price,
    change_rate: changeRate,
    per: 13.2,
    pbr: 1.42,
    eps: Math.round(price / 13.2),
    bps: Math.round(price / 1.42),
    week52_high: week52High,
    week52_low: week52Low,
    market_cap: price * 5_969_782_550,
    as_of: '20260703',
  },
  // 재무추이(억원 단위). 실데이터 아님 — 표 렌더 확인용 4개년.
  financials: {
    income: [
      { period: '202112', revenue: 2_796_000, operating_income: 516_000, net_income: 399_000 },
      { period: '202212', revenue: 3_022_000, operating_income: 433_000, net_income: 556_000 },
      { period: '202312', revenue: 2_589_000, operating_income: 65_000, net_income: 154_000 },
      { period: '202412', revenue: 3_008_000, operating_income: 329_000, net_income: 341_000 },
    ],
    ratio: [
      { period: '202112', eps: 5777, bps: 43_611, roe: 13.9 },
      { period: '202212', eps: 8057, bps: 50_817, roe: 17.1 },
      { period: '202312', eps: 2131, bps: 52_002, roe: 4.1 },
      { period: '202412', eps: 4950, bps: 55_800, roe: 9.2 },
    ],
    year_end_prices: { 202112: 78300, 202212: 55300, 202312: 78500, 202412: 53000 },
  },
  chart: { candles: CANDLES },
  summary: {
    rev_cagr: 2.5, // 이미 %(엔진이 ×100 반환). (3008000/2796000)^(1/3)-1 ≈ 2.5%
    op_cagr: -14.0,
    current_per: 13.2,
    avg_per: 11.8,
    per_vs_avg: 11.9, // 이미 %  (13.2-11.8)/11.8*100
    valuation_label: '고평가', // +11.9% > +10% 밴드 → 고평가 (코드 확정, LLM 불가변)
    rsi: 58.3,
    ma20_gap_pct: 2.4,
    pos_52w_pct: 72.5,
    sample_years: 4,
    notes: [],
  },
  regime_gate: {
    regime: '확장',
    per_max: 25,
    pbr_max: 3.0,
    single_cap: 20,
    per_over: false,
    pbr_over: false,
    entry_blocked: false,
    note: '확장 국면 기준 이내 — PER 13.2 ≤ 25, PBR 1.42 ≤ 3.0. (사실 서술이며 매매 권유가 아님)',
  },
  // 예측 PER(리서치 컨센서스) — 현재가 ÷ 예측 EPS. 후행 PER 13.2 대비 낮아짐(실적 성장 전망 반영).
  forward_valuation: {
    forward_per: [
      { period: '202612', eps: 6100, forward_per: 10.9, kis_per: 10.5 },
      { period: '202712', eps: 7200, forward_per: 9.2, kis_per: 9.0 },
    ],
    prev_year_per: 13.0, // 직전년도(2025) PER — 현재가 기준, 예측과 함께 추이 표시
    prev_year_period: '202512',
    analyst: '김한국',
    est_date: '20260630',
    recommendation: '매수',
  },
  indicator_config: { ma_period: 20, rsi_period: 14 },
  partial_failure: [],
}
