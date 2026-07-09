// 팝업 라우팅(순수) — chat 응답 popups[].name → 컴포넌트 kind 로 분기한다.
// 계약: chat 응답 = {text, popups:[{name, args}]} (llm-engineer chat/tools.py 3종 툴).
// 원칙: 라우팅은 name 으로만 판단하고 args(enum)는 통과시킨다. 팝업 실데이터는 LLM 이 아니라
//   프론트 컴포넌트가 API 로 직접 조회한다(환각 차단 + 최신성). 미지의 name 은 조용히 제외한다.
//
//   show_stock_report   → 'stock_report'  : StockReportView 모달(args.ticker 로 fetchStockBundle)
//   show_macro_dashboard → 'macro_dashboard': RegimeGauge 모달(fetchMacroRegime, 자체 조회·무캐시)
//   show_watchlist       → 'watchlist'     : W10 플레이스홀더
import { isValidTicker } from './ticker.js'

// 라우팅 계약 상수(SSOT) — 여기 없는 툴 이름은 라우팅되지 않는다(오발동·주입 방지).
export const POPUP_KIND = {
  show_stock_report: 'stock_report',
  show_macro_dashboard: 'macro_dashboard',
  show_watchlist: 'watchlist',
}

// 단일 팝업 → 모달 스펙 {kind, name, args, valid} 또는 null(미지·결측).
// valid: show_stock_report 는 ticker 형식 검증(isValidTicker, ticker.js SSOT — 직접입력과 동일 규칙)
//   결과, 그 외는 항상 true(ticker 불요). 불량이면 조회 없이 컴포넌트가 안내만 한다(잘못된 백엔드 조회 방지).
export function routePopup(popup) {
  if (!popup || typeof popup.name !== 'string') return null
  const kind = POPUP_KIND[popup.name]
  if (!kind) return null
  const args = popup.args ?? {}
  const valid = kind === 'stock_report' ? isValidTicker(args.ticker) : true
  return { kind, name: popup.name, args, valid }
}

// popups 배열 → 유효 모달 스펙 리스트(순서 보존, 미지/결측 제외). 비배열 → [].
export function routePopups(popups) {
  if (!Array.isArray(popups)) return []
  return popups.map(routePopup).filter(Boolean)
}
