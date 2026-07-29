import { readChatStream } from './lib/sseChat.js'
import { readSSE } from './lib/sse.js'
import { authFetch } from './auth.js'

// 백엔드(FastAPI) 호출 헬퍼. 엔드포인트 계약은 api/main.py 와 일치해야 한다.
//
// ── 내부 공용 요청 헬퍼(_request) — 44개 함수가 반복하던 보일러플레이트의 단일 출처 ──
// (리팩토링 2026-07-29 · characterization 테스트 41건[api.test.js]으로 관측 동작 고정 후 통합)
// 동작 변형은 옵션 플래그로만 표현한다(기존 각 함수의 에러 shape 를 그대로 보존):
//   auth:      true 면 authFetch(Bearer 주입 — 로그인 시 본인 스코프/KIS 키), false 면 공개 fetch.
//   method:    미지정이면 GET(옵션 객체 자체를 생략해 fetch(url) 1-인자 호출 — 기존 호출형 보존).
//   json:      JSON 바디(지정 시 Content-Type 헤더 + stringify).
//   errStatus: 실패 Error 에 res.status 를 .status 로 부착(호출부 분기 — 409 상한·403 관리자 등).
//   errDetail: 실패 시 응답 JSON 의 detail 메시지를 우선 사용(서버 안내문 표면화 — KIS 검증 실패 등).
//              이 모드는 성공 시에도 '미리 파싱한 JSON'을 반환한다(빈 바디는 {} 로 방어).
// 성공은 res.json() 반환, 실패는 `API {status}` Error throw — 항상 200 graceful 인 엔드포인트는
// 여기서 throw 되지 않는다(throw 는 네트워크/HTTP 오류만이라는 각 함수 주석과 일치).
async function _request(url, { method, json, auth = false, errStatus = false, errDetail = false } = {}) {
  const doFetch = auth ? authFetch : fetch
  const opts = {}
  if (method) opts.method = method
  if (json !== undefined) {
    opts.headers = { 'Content-Type': 'application/json' }
    opts.body = JSON.stringify(json)
  }
  // GET(옵션 없음)은 1-인자 호출 — fetch(url). (characterization: toHaveBeenCalledWith(url))
  const res = Object.keys(opts).length > 0 ? await doFetch(url, opts) : await doFetch(url)
  if (errDetail) {
    // 서버 detail 안내문을 쓰는 계열 — 성공/실패 모두 바디를 먼저 파싱(빈 바디는 {} 방어).
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      const err = new Error(data.detail || `API ${res.status}`)
      if (errStatus) err.status = res.status
      throw err
    }
    return data
  }
  if (!res.ok) {
    const err = new Error(`API ${res.status}`)
    if (errStatus) err.status = res.status // 호출부 분기용(addErrorMessage 등) — 플래그 켠 계열만
    throw err
  }
  return res.json()
}

export async function fetchMacroIndicators() {
  return _request('/api/macro/indicators')
}

// 국면 판정(매크로 엔진, W07). judge_regime 결과 + indicators_used + partial_failure.
// 2축 계약(구 votes·override → axes·vix_panic 으로 대체·폐기):
// shape: {regime, recommended_cash_ratio, confidence,
//         axes:{cycle:{score,sign}, sentiment:{score,sign}},   // sign: 경기=양호/중립/악화, 심리=탐욕/중립/공포
//         key_drivers:[[label, axis, direction]...],            // axis: 경기|심리, direction: 양호|악화|탐욕|공포
//         params, vix_panic, missing_indicators, raw_data,      // vix_panic: vix>35 표시 플래그(오버라이드 아님)
//         indicators_used, partial_failure,
//         indicator_breakdown:[{key,label,value,unit,zone,axis,source,thresholds:{lo,hi}}...]}  // 판정근거 카드
export async function fetchMacroRegime() {
  return _request('/api/macro/regime')
}

// 국면 지표 1개의 월단위 히스토리(카드 클릭). GET /api/macro/indicators/{key}/history?months=
// → {key, label, unit, source, thresholds:{lo,hi}, months, points:[{date,value}], available, note?}.
// 항상 200 graceful — 불가·실패는 available:false + note(fear_greed 는 best-effort). 불량 key 는 400.
export async function fetchMacroIndicatorHistory(key, months = 12) {
  return _request(`/api/macro/indicators/${encodeURIComponent(key)}/history?months=${months}`)
}

// 국면 이동 궤적(족적) — 최근 N개월 월별 국면 판정을 엔진으로 재현. GET /api/macro/regime/history?months=
// → {months, interval:"monthly", points:[{date, cycle_score, sentiment_score, regime,
//    recommended_cash_ratio, vix_panic, missing_indicators}], available, partial_failure, note?}.
// 항상 200 graceful — 불가/실패는 available:false + note(공포탐욕 결측이어도 심리축은 VIX 로 판정).
// 판정은 코드(엔진 결정적 재현)이지 예측이 아니다.
export async function fetchRegimeTrajectory(months = 36) {
  return _request(`/api/macro/regime/history?months=${months}`)
}

// 사이트 통계 — 방문 1건 기록(앱 로드 시 1회) + 가입자·방문 집계 조회. 공개·집계만(PII 없음).
// 실패는 호출부(App)가 graceful 처리(칩만 생략).
export async function recordVisit() {
  return _request('/api/visit', { method: 'POST' })
}

export async function fetchSiteStats() {
  return _request('/api/stats')
}

// 종목 종합리포트 번들(W08). GET /api/detail/{ticker}/bundle 을 1회 호출한다(N+1 금지).
// 응답 계약(계획 "번들 계약"): {ticker, basic|null, valuation|null, financials|null, chart|null,
//   summary|null, forward_valuation|null, indicator_config:{ma_period,rsi_period}, partial_failure:[]}.
//   (국면정합성 게이트 regime_gate 는 폐기 — 항목3, 번들은 국면과 무관.)
// 섹션 실패는 null + partial_failure 로 오고 항상 200 — 그건 정상 응답이라 throw 하지 않는다.
// 여기서 throw 하는 건 네트워크/HTTP 오류(백엔드 미연결 등)뿐이다.
// authFetch — 로그인 시 토큰을 실어 백엔드가 본인 KIS 키로 조회(미로그인/미등록은 공유 fallback).
export async function fetchStockBundle(ticker) {
  return _request(`/api/detail/${encodeURIComponent(ticker)}/bundle`, { auth: true })
}

// 선택형 차트 — 일봉/주봉 × 3개월/1년/3년/10년. GET /api/detail/{ticker}/chart?period=&range=
// → {ticker, period, range, candles:[...], stage_segments:[{stage,start_date,end_date}], current_stage,
//    partial_failure:[]}. 장기간은 백엔드 페이지네이션(KIS ~100/콜). 스테이지 리본은 표시 시계열로 재계산.
// **정량 요약(RSI/MA/현재 대순환 단계)은 번들[일봉]에 pin** — 차트 탐색이 판정을 바꾸지 않는다.
// KIS 실패는 항상 200 graceful(빈 candles + partial_failure). throw 는 네트워크/HTTP 오류만.
export async function fetchStockChart(ticker, period = 'D', range = '1y') {
  const qs = new URLSearchParams({ period, range })
  return _request(`/api/detail/${encodeURIComponent(ticker)}/chart?${qs}`, { auth: true })
}

// ── 대화기록(대화 목록·생성·메시지·삭제, 유저 스코프) ─────────────────────────
// session_id(챗)는 conversation.id 를 쓴다. 모두 인증 필수(authFetch).

// GET /api/conversations → {conversations:[{id, title, created_at, updated_at}]}(최근 갱신순).
export async function fetchConversations() {
  return _request('/api/conversations', { auth: true })
}

// POST /api/conversations {title?} → {id, title, created_at, updated_at}. 새 대화 생성.
export async function createConversation(title) {
  return _request('/api/conversations', { method: 'POST', json: { title: title ?? null }, auth: true })
}

// GET /api/conversations/{id}/messages → {conversation, messages:[{role, content, created_at}]}.
export async function fetchConversationMessages(conversationId) {
  return _request(`/api/conversations/${encodeURIComponent(conversationId)}/messages`, { auth: true })
}

// PATCH /api/conversations/{id} {title} → {id, title, ...}. 대화 이름 수정(소유권 검증·빈 제목 422).
export async function renameConversation(conversationId, title) {
  return _request(`/api/conversations/${encodeURIComponent(conversationId)}`, {
    method: 'PATCH',
    json: { title },
    auth: true,
  })
}

// DELETE /api/conversations/{id} → {ok}. 대화 삭제(메시지 cascade).
export async function deleteConversation(conversationId) {
  return _request(`/api/conversations/${encodeURIComponent(conversationId)}`, {
    method: 'DELETE',
    auth: true,
  })
}

// 챗봇(W09). POST /api/chat body {session_id, message} → {text, popups:[{name, args}]}.
// text=말풍선, popups=팝업 트리거(name→컴포넌트, args=enum·ticker). 팝업 실데이터는 여기가 아니라
// 프론트 컴포넌트가 fetchStockBundle/fetchMacroRegime 로 직접 조회한다(환각 차단, frontend-engineer 원칙2).
// 세션 히스토리는 서버가 session_id 로 보관(슬라이딩 윈도우) — 프론트는 id+메시지만 보낸다.
export async function postChat(sessionId, message) {
  return _request('/api/chat', {
    method: 'POST',
    json: { session_id: sessionId, message },
    auth: true,
  })
}

// 챗봇 SSE 스트리밍(W09). POST /api/chat/stream body {session_id, message} → text/event-stream.
// 진행 단계(stage)·토큰(token)·팝업(popups)·완료(done) 이벤트를 도착하는 대로 handlers 로 흘린다.
// POST+body 라 EventSource 대신 fetch 스트림(readChatStream)을 쓴다. 기존 postChat 는 폴백용으로 유지.
// 팝업 실데이터는 여기가 아니라 프론트 컴포넌트가 직접 조회한다(환각 차단, 논스트림과 동일).
// SSE 는 res.json() 이 아니라 스트림 리더 소비라 _request 를 쓰지 않는다(전용 경로).
export async function postChatStream(sessionId, message, handlers = {}) {
  let res
  try {
    res = await authFetch('/api/chat/stream', {
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
// 시세 등 실데이터는 여기(프론트)가 직접 조회한다(환각 차단) — LLM 응답에서 꺼내지 않는다.

// GET /api/watchlist?sort_by= → {items:[{ticker, stock_name, reason, target_price, added_at,
//   current_price, change_rate, per, pbr, spark, distance_to_target, target_status}],
//   regime:{regime}, sort_by, partial_failure:[]}.  (국면별 종목 진입신호 entry_signal 폐기 — 항목3)
// 시세 실패 종목은 값 null + partial_failure 에 ticker(부분실패 보존). 항상 200 — throw 는 네트워크/HTTP 오류만.
// sort_by 는 서버가 에코만 하고 실제 정렬은 프론트(watchlistLogic.sortItems)가 재조회 없이 수행.
export async function fetchWatchlist(sortBy) {
  const qs = sortBy ? `?sort_by=${encodeURIComponent(sortBy)}` : ''
  return _request(`/api/watchlist${qs}`, { auth: true })
}

// GET /api/watchlist/{ticker} → {ticker, member}. 경량 멤버십(시세 조회 없음) — 추가/제거 버튼 토글용.
export async function fetchWatchlistMembership(ticker) {
  return _request(`/api/watchlist/${encodeURIComponent(ticker)}`, { auth: true })
}

// POST /api/watchlist {ticker, stock_name?, reason?, target_price?} → {ok, item}. upsert(중복=갱신, added_at 보존).
// stock_name 없으면 백엔드가 KIS 마스터/시세로 해석. 상태코드: 불량 ticker=400(api.deps.assert_valid_ticker),
// 상한 초과=409, target 음수=422(Pydantic ge=0) — err.status 로 실어 addErrorMessage 가 분기 안내.
export async function addWatchlist({ ticker, stockName, reason, targetPrice, sellTargetPrice } = {}) {
  // 옵션 키는 값이 있을 때만 바디에 포함(부분 upsert — 미제공 목표가는 기존값 보존, 백엔드 계약).
  const body = { ticker }
  if (stockName != null) body.stock_name = stockName
  if (reason != null) body.reason = reason
  if (targetPrice != null) body.target_price = targetPrice
  if (sellTargetPrice != null) body.sell_target_price = sellTargetPrice
  return _request('/api/watchlist', { method: 'POST', json: body, auth: true, errStatus: true })
}

// DELETE /api/watchlist/{ticker} → {ok}. err.status 부착(IMP-10 — addErrorMessage 분기).
export async function removeWatchlist(ticker) {
  return _request(`/api/watchlist/${encodeURIComponent(ticker)}`, {
    method: 'DELETE',
    auth: true,
    errStatus: true,
  })
}

// PATCH /api/watchlist/{ticker} {target_price?, sell_target_price?} → {ok, item}.
// targets 객체에 있는 키만 전송(백엔드가 model_fields_set 로 부분 갱신) — 매수/매도를 독립 설정.
// 값 null 은 '해제', 키 부재는 '변경 안 함'. 매수만: {target_price}, 매도만: {sell_target_price}.
export async function updateWatchlistTarget(ticker, targets) {
  return _request(`/api/watchlist/${encodeURIComponent(ticker)}`, {
    method: 'PATCH',
    json: targets || {},
    auth: true,
    errStatus: true,
  })
}

// ── AI 종합 리포트(W10 P2) ──────────────────────────────────────────────────
// LLM 은 서술만 생성하고 판정·숫자는 코드가 확정한다(역할 분리). Pydantic StockReport 로 검증된
// 구조화 리포트만 반환 — 리스크요인 최소 1개·면책 필수는 백엔드 스키마가 강제한다.

// POST /api/detail/{ticker}/report → {ticker, report:{종합의견,요약,투자포인트,리스크요인,국면정합성,
//   면책고지}|null, validation_failed, quant_summary, message, regime_at_creation, created_at}.
// 검증 실패 시 report=null + validation_failed=true + message(정량요약은 quant_summary 로 보존). 항상 200.
export async function generateStockReport(ticker) {
  return _request(`/api/detail/${encodeURIComponent(ticker)}/report`, { method: 'POST', auth: true })
}

// GET /api/detail/{ticker}/report/history → {ticker, history:[{created_at, regime_at_creation, report_json}]}.
// created_at 내림차순(최신 우선). 빈 종목은 history:[](과거 대비 비교 데모).
export async function fetchReportHistory(ticker) {
  return _request(`/api/detail/${encodeURIComponent(ticker)}/report/history`, { auth: true })
}

// ── 잔고(포트폴리오, UX 개편) ────────────────────────────────────────────────
// GET /api/balance → {holdings:[{ticker,name,qty,avg_price,current_price,eval_amount,pnl_amount,pnl_pct,
//   spark:number[]|null}], summary:{deposit,purchase_amount,eval_amount,pnl_amount,total_eval,net_asset},
//   partial_failure:[]}. spark 는 관심종목과 동일한 미니 스파크라인(일봉 종가 시계열, 실패 시 null).
// 조회 전용(주문/매매 없음). 현재가 포함 → 캐시 없음(원칙1) — 팝업 열 때마다 조회. KIS 실패 시
// holdings=null·summary=null·partial_failure:['balance'](항상 200) → 컴포넌트가 graceful 안내.
// 여기서 throw 하는 건 네트워크/HTTP 오류(백엔드 미연결 등)뿐이다.
export async function fetchBalance() {
  // 로그인 시 본인 계좌, 아니면 공유 데모 계좌
  return _request('/api/balance', { auth: true })
}

// 대순환 후보 스크리너 — 시총상위 유니버스를 대순환 단계로 스캔. market: all/kospi/kosdaq/kospi200.
export async function fetchScreener(market = 'all', size = 30) {
  return _request(`/api/screener?market=${encodeURIComponent(market)}&size=${size}`, { auth: true })
}

// ── 유저별 KIS 자격증명(설정) ────────────────────────────────────────────────
// GET /api/me/kis-credentials → {registered, source:'user'|'shared'|'none', app_key_masked, account_masked, env}.
// 마스킹 상태만(원문 미반환). 인증 필수.
export async function fetchKisCredentialsStatus() {
  return _request('/api/me/kis-credentials', { auth: true })
}

// POST /api/me/kis-credentials {app_key, app_secret, account_no?, acnt_prdt_cd?, env?} → {ok, status}.
// 서버가 실제 KIS 토큰 발급으로 검증 후 암호화 저장. 검증 실패 400(키 값은 서버·응답에 미노출) —
// errDetail 로 서버 detail 안내문(실패 사유)을 그대로 표면화한다.
export async function setKisCredentials(body) {
  return _request('/api/me/kis-credentials', {
    method: 'POST',
    json: body,
    auth: true,
    errDetail: true,
  })
}

// DELETE /api/me/kis-credentials → {ok, status}. 본인 키 삭제(이후 공유 fallback).
export async function deleteKisCredentials() {
  return _request('/api/me/kis-credentials', { method: 'DELETE', auth: true })
}

// ── 시황(market outlook) 요약 — 시장 국면 페이지 ─────────────────────────────
// 시황 요약은 '증권사 시황 리포트 인용'(에이전트 시장 판정 아님)·출처 귀속·면책. 시장 판정은 코드(매크로 엔진).

// GET /api/macro/market-outlook → {reports:[{report_id, broker, title, date, pdf_url,
//   summary:{증권사,제목,시장전망,요약,핵심요지[],리스크요인[],면책고지}, created_at}]}. 없으면 reports:[].
export async function fetchMarketOutlook() {
  return _request('/api/macro/market-outlook')
}

// POST /api/macro/market-outlook/summary → 최근 5개 시황 종합 '금일의 요약'(10줄). 온디맨드·항상 200.
export async function fetchMarketOutlookSummary() {
  return _request('/api/macro/market-outlook/summary', { method: 'POST' })
}

// POST /api/macro/market-outlook/fetch?limit=N → {fetched, new, skipped, failed}. 네이버 최신 시황
// 수집·요약(서버, idempotent). 항상 200. 완료 후 fetchMarketOutlook 재조회.
export async function fetchNaverMarketOutlook(limit = 15) {
  return _request(`/api/macro/market-outlook/fetch?limit=${limit}`, { method: 'POST' })
}

// ── 애널리스트 리포트(네이버 수집 · 종목별 요약 · 챗 상담 연계) ────────────────
// 요약·자문은 '리포트 내용 인용'(에이전트 자체 매수/매도 판정 아님)이며 출처 귀속·면책 상시.
// 실데이터(요약)는 프론트가 아래 GET 으로 직접 조회한다(환각 차단) — LLM 응답에서 꺼내지 않는다.

// GET /api/detail/{ticker}/analyst-reports → {ticker, reports:[{report_id, broker, stock_name,
//   title, date, pdf_url, summary:{증권사,종목,목표주가,투자의견,요약,핵심요지[],리스크요인[],면책고지},
//   created_at}]}. 저장된 게 없으면 reports:[]. throw 는 네트워크/HTTP 오류만.
export async function fetchAnalystReports(ticker) {
  return _request(`/api/detail/${encodeURIComponent(ticker)}/analyst-reports`)
}

// POST /api/detail/{ticker}/analyst-reports/summary → {ticker, summary|null, validation_failed,
//   report_count, message?}. 저장된 최근 3개 리포트를 서버가 LLM 으로 종합(10줄)해 반환(온디맨드,
//   PDF 재다운로드 없음). summary={종목,의견분포,목표주가범위,종합요약[],면책고지}. 0개·검증실패는
//   validation_failed=true(항상 200). throw 는 네트워크/HTTP 오류만.
export async function fetchAnalystReportsSummary(ticker) {
  return _request(`/api/detail/${encodeURIComponent(ticker)}/analyst-reports/summary`, {
    method: 'POST',
  })
}

// POST /api/reports/fetch?limit=N → {fetched, new, skipped, failed}. 네이버 최신 리포트를 서버가
// 수집·요약·저장(idempotent). 항상 200(수집/요약 실패는 graceful 카운트). 완료 후 fetchAnalystReports 재조회.
export async function fetchNaverReports(limit = 20) {
  return _request(`/api/reports/fetch?limit=${limit}`, { method: 'POST' })
}

// SSE 진행 스트림 — 이 종목 리포트 수집·요약. onEvent 로 {stage|found|progress|done|error} 이벤트 전달
// (실시간 체크리스트). 스트림 끊김/미지원 시 onError → 컴포넌트가 non-stream fetchNaverStockReports 폴백.
// SSE 는 스트림 리더 소비(res.json() 아님)라 _request 미사용(전용 경로).
export async function streamFetchStockReports(ticker, { onEvent, onError, limit = 10 } = {}) {
  try {
    const res = await fetch(
      `/api/detail/${encodeURIComponent(ticker)}/analyst-reports/fetch/stream?limit=${limit}`,
      { method: 'POST' },
    )
    await readSSE(res, onEvent, onError)
  } catch (e) {
    onError?.(e)
  }
}

// SSE 진행 스트림 — 네이버 최신 시황 수집·요약(위와 동형).
export async function streamFetchMarketOutlook({ onEvent, onError, limit = 15 } = {}) {
  try {
    const res = await fetch(`/api/macro/market-outlook/fetch/stream?limit=${limit}`, {
      method: 'POST',
    })
    await readSSE(res, onEvent, onError)
  } catch (e) {
    onError?.(e)
  }
}

// POST /api/detail/{ticker}/analyst-reports/fetch?limit=N → {fetched, new, skipped, failed}.
// **이 종목**의 네이버 리포트만 수집·요약(itemCode 필터, 전체 최신 피드 아님). 항상 200(graceful).
// 종목 상세 "이 종목 리포트 가져오기". 완료 후 fetchAnalystReports(ticker) 재조회. (SSE 폴백용.)
export async function fetchNaverStockReports(ticker, limit = 10) {
  return _request(`/api/detail/${encodeURIComponent(ticker)}/analyst-reports/fetch?limit=${limit}`, {
    method: 'POST',
  })
}

// POST /api/chat/report-context {session_id, ticker, report_id} → {ok, set, broker?}.
// 저장된 리포트 요약을 세션 상담 컨텍스트로 핀 고정(이후 후속 질문이 그 리포트 근거로 답변).
// **요약 본문은 보내지 않는다** — 서버가 store 에서 조회(환각·조작 차단). ticker/reportId 가 없으면 해제.
export async function setReportContext(sessionId, ticker, reportId) {
  return _request('/api/chat/report-context', {
    method: 'POST',
    json: { session_id: sessionId, ticker: ticker ?? null, report_id: reportId ?? null },
  })
}

// 시황(매크로) 리포트로 상담 — 애널리스트와 동일 세션 핀 슬롯. 시황은 시장 전체라 ticker 없음.
export async function setMarketOutlookContext(sessionId, reportId) {
  return _request('/api/chat/market-outlook-context', {
    method: 'POST',
    json: { session_id: sessionId, report_id: reportId ?? null },
  })
}

// POST /api/chat/context {session_id, kind, args} → {ok, set, kind?}. 사용자가 현재 보고 있는 화면
// (잔고·관심종목·종목상세)을 세션 핀 컨텍스트로 고정 → 이후 챗 질문이 그 데이터를 근거로 답변.
// **화면 데이터는 보내지 않는다** — 서버가 kind/args 로 재조회(환각·조작 차단). 비데이터 kind/조회불가는 해제.
export async function setViewContext(sessionId, kind, args = {}) {
  return _request('/api/chat/context', {
    method: 'POST',
    json: { session_id: sessionId, kind: kind ?? null, args: args ?? {} },
  })
}

// 종목 자동완성(W08). GET /api/stocks/search?q=&limit= → [{ticker, name, market}].
// KIS 마스터(코스피+코스닥 전 종목) 기반. 실패 시 빈 배열(프론트는 코드 직접 입력 폴백).
export async function searchStocks(query, limit = 8) {
  const data = await _request(`/api/stocks/search?q=${encodeURIComponent(query)}&limit=${limit}`)
  return data.results ?? []
}

// ── 관리자 — 유저 관리·이용 통계·질문 한도 제어 ────────────────────────────────
// 전부 authFetch(Bearer) + get_admin_user 게이트(비관리자 403). 매매·자격증명 원문 무관(조회/제어만).
// 403 분기(AdminPanel 안내)를 위해 전 함수 errStatus, 서버 안내문(자기 자신 해제/삭제 400 등)이 있는
// PATCH/DELETE 는 errDetail 도 켠다.

// GET /api/admin/users → {users:[{id,email,is_admin,daily_limit,used_today,remaining,total_questions,created_at}]}.
export async function fetchAdminUsers() {
  const data = await _request('/api/admin/users', { auth: true, errStatus: true })
  return data.users ?? []
}

// PATCH /api/admin/users/{id} {is_admin?, daily_limit?} → 갱신된 유저. 자기 자신 관리자해제=400.
export async function updateAdminUser(userId, patch) {
  return _request(`/api/admin/users/${encodeURIComponent(userId)}`, {
    method: 'PATCH',
    json: patch,
    auth: true,
    errStatus: true,
    errDetail: true,
  })
}

// POST /api/admin/users/{id}/reset-usage → 갱신된 유저(오늘 사용량 0, 누적 통계 보존).
export async function resetAdminUserUsage(userId) {
  return _request(`/api/admin/users/${encodeURIComponent(userId)}/reset-usage`, {
    method: 'POST',
    auth: true,
    errStatus: true,
  })
}

// DELETE /api/admin/users/{id} → {ok, deleted}. 유저 + 스코프 데이터 삭제. 자기 자신 삭제=400.
export async function deleteAdminUser(userId) {
  return _request(`/api/admin/users/${encodeURIComponent(userId)}`, {
    method: 'DELETE',
    auth: true,
    errStatus: true,
    errDetail: true,
  })
}
