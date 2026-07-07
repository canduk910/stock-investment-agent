// 백엔드(FastAPI) 호출 헬퍼. 엔드포인트 계약은 api/main.py 와 일치해야 한다.
export async function fetchMacroIndicators() {
  const res = await fetch('/api/macro/indicators')
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.json()
}

// 국면 판정(매크로 엔진, W07). judge_regime 결과 + indicators_used + partial_failure.
// 2축 계약(구 votes·override → axes·vix_panic 으로 대체·폐기):
// shape: {regime, recommended_cash_ratio, confidence,
//         axes:{cycle:{score,sign}, sentiment:{score,sign}},   // sign: 경기=양호/중립/악화, 심리=탐욕/중립/공포
//         key_drivers:[[label, axis, direction]...],            // axis: 경기|심리, direction: 양호|악화|탐욕|공포
//         params, vix_panic, missing_indicators, raw_data,      // vix_panic: vix>35 표시 플래그(오버라이드 아님)
//         indicators_used, partial_failure}
export async function fetchMacroRegime() {
  const res = await fetch('/api/macro/regime')
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.json()
}

// 종목 종합리포트 번들(W08). GET /api/detail/{ticker}/bundle 을 1회 호출한다(N+1 금지).
// 응답 계약(계획 "번들 계약"): {ticker, basic|null, valuation|null, financials|null, chart|null,
//   summary|null, regime_gate|null, indicator_config:{ma_period,rsi_period}, partial_failure:[]}.
// 섹션 실패는 null + partial_failure 로 오고 항상 200 — 그건 정상 응답이라 throw 하지 않는다.
// 여기서 throw 하는 건 네트워크/HTTP 오류(백엔드 미연결 등)뿐이다.
export async function fetchStockBundle(ticker) {
  const res = await fetch(`/api/detail/${encodeURIComponent(ticker)}/bundle`)
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.json()
}

// 종목 자동완성(W08). GET /api/stocks/search?q=&limit= → [{ticker, name, market}].
// KIS 마스터(코스피+코스닥 전 종목) 기반. 실패 시 빈 배열(프론트는 코드 직접 입력 폴백).
export async function searchStocks(query, limit = 8) {
  const res = await fetch(
    `/api/stocks/search?q=${encodeURIComponent(query)}&limit=${limit}`,
  )
  if (!res.ok) throw new Error(`API ${res.status}`)
  const data = await res.json()
  return data.results ?? []
}
