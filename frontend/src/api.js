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

// ── 워치리스트(W10) ─────────────────────────────────────────────────────────
// 엔드포인트 계약은 api/watchlist.py 와 일치. 단일 로컬 사용자라 user_id 는 전달하지 않는다(기본 "local").
// 시세·진입신호 등 실데이터는 여기(프론트)가 직접 조회한다(환각 차단) — LLM 응답에서 꺼내지 않는다.

// GET /api/watchlist?sort_by= → {items:[{ticker, stock_name, reason, target_price, added_at,
//   current_price, change_rate, per, pbr, distance_to_target, target_status, entry_signal}],
//   regime:{regime, single_cap, entry_blocked}, sort_by, partial_failure:[]}.
// 시세 실패 종목은 값 null + partial_failure 에 ticker(부분실패 보존). 항상 200 — throw 는 네트워크/HTTP 오류만.
// sort_by 는 서버가 에코만 하고 실제 정렬은 프론트(watchlistLogic.sortItems)가 재조회 없이 수행.
export async function fetchWatchlist(sortBy) {
  const qs = sortBy ? `?sort_by=${encodeURIComponent(sortBy)}` : ''
  const res = await fetch(`/api/watchlist${qs}`)
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.json()
}

// POST /api/watchlist {ticker, stock_name?, reason?, target_price?} → {ok, item}. upsert(중복=갱신, added_at 보존).
// stock_name 없으면 백엔드가 KIS 마스터/시세로 해석. ticker 불량은 백엔드 Pydantic 이 422 로 거른다.
export async function addWatchlist({ ticker, stockName, reason, targetPrice } = {}) {
  const body = { ticker }
  if (stockName != null) body.stock_name = stockName
  if (reason != null) body.reason = reason
  if (targetPrice != null) body.target_price = targetPrice
  const res = await fetch('/api/watchlist', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    // status 를 에러에 실어 호출부가 분기(409=상한 초과 등, watchlistLogic.addErrorMessage 로 안내).
    const err = new Error(`API ${res.status}`)
    err.status = res.status
    throw err
  }
  return res.json()
}

// DELETE /api/watchlist/{ticker} → {ok}.
export async function removeWatchlist(ticker) {
  const res = await fetch(`/api/watchlist/${encodeURIComponent(ticker)}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.json()
}

// PATCH /api/watchlist/{ticker} {target_price} → {ok, item}. 목표가 설정/변경(null 이면 해제).
export async function updateWatchlistTarget(ticker, targetPrice) {
  const res = await fetch(`/api/watchlist/${encodeURIComponent(ticker)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_price: targetPrice }),
  })
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.json()
}

// ── AI 종합 리포트(W10 P2) ──────────────────────────────────────────────────
// LLM 은 서술만 생성하고 판정·숫자는 코드가 확정한다(역할 분리). Pydantic StockReport 로 검증된
// 구조화 리포트만 반환 — 리스크요인 최소 1개·면책 필수는 백엔드 스키마가 강제한다.

// POST /api/detail/{ticker}/report → {ticker, report:{종합의견,요약,투자포인트,리스크요인,국면정합성,
//   면책고지}|null, validation_failed, quant_summary, message, regime_at_creation, created_at}.
// 검증 실패 시 report=null + validation_failed=true + message(정량요약은 quant_summary 로 보존). 항상 200.
export async function generateStockReport(ticker) {
  const res = await fetch(`/api/detail/${encodeURIComponent(ticker)}/report`, { method: 'POST' })
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.json()
}

// GET /api/detail/{ticker}/report/history → {ticker, history:[{created_at, regime_at_creation, report_json}]}.
// created_at 내림차순(최신 우선). 빈 종목은 history:[](과거 대비 비교 데모).
export async function fetchReportHistory(ticker) {
  const res = await fetch(`/api/detail/${encodeURIComponent(ticker)}/report/history`)
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
