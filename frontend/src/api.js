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
