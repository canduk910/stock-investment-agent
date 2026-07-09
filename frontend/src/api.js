import { readChatStream } from './lib/sseChat.js'

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

// 챗봇(W09). POST /api/chat body {session_id, message} → {text, popups:[{name, args}]}.
// text=말풍선, popups=팝업 트리거(name→컴포넌트, args=enum·ticker). 팝업 실데이터는 여기가 아니라
// 프론트 컴포넌트가 fetchStockBundle/fetchMacroRegime 로 직접 조회한다(환각 차단, frontend-engineer 원칙2).
// 세션 히스토리는 서버가 session_id 로 보관(슬라이딩 윈도우) — 프론트는 id+메시지만 보낸다.
export async function postChat(sessionId, message) {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }),
  })
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.json()
}

// 챗봇 SSE 스트리밍(W09). POST /api/chat/stream body {session_id, message} → text/event-stream.
// 진행 단계(stage)·토큰(token)·팝업(popups)·완료(done) 이벤트를 도착하는 대로 handlers 로 흘린다.
// POST+body 라 EventSource 대신 fetch 스트림(readChatStream)을 쓴다. 기존 postChat 는 폴백용으로 유지.
// 팝업 실데이터는 여기가 아니라 프론트 컴포넌트가 직접 조회한다(환각 차단, 논스트림과 동일).
export async function postChatStream(sessionId, message, handlers = {}) {
  let res
  try {
    res = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message }),
    })
  } catch (e) {
    // 네트워크 자체 실패(백엔드 미연결 등) — 스트림 진입 전이라 onError 로 폴백 유도.
    handlers.onError?.(e)
    return
  }
  await readChatStream(res, handlers)
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
