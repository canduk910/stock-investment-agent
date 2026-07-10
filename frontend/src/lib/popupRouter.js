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
  manage_watchlist: 'manage_watchlist', // IMP-08: 자연어 편집 → 화면 confirm 후 반영(자동 매매 아님)
}

// manage_watchlist 유효 action(워치리스트 편집만 — buy/sell 등 매매 어휘는 애초에 매핑되지 않음).
const MANAGE_ACTIONS = new Set(['add', 'remove', 'set_target'])

function isValidManage(args) {
  if (!MANAGE_ACTIONS.has(args.action)) return false
  if (!isValidTicker(args.ticker)) return false
  if (args.action === 'set_target') {
    const n = Number(args.target_price)
    return Number.isFinite(n) && n >= 0 // 목표가 설정은 유효 수치(>=0) 필수
  }
  return true
}

// 단일 팝업 → 모달 스펙 {kind, name, args, valid} 또는 null(미지·결측).
// valid: show_stock_report 는 ticker 형식(isValidTicker, ticker.js SSOT), manage_watchlist 는
//   action enum+ticker(+set_target 은 target_price>=0) 검증. 그 외 true. 불량이면 조회/실행 없이
//   컴포넌트가 안내만 한다(잘못된 백엔드 조회·의도치 않은 편집 방지).
export function routePopup(popup) {
  if (!popup || typeof popup.name !== 'string') return null
  const kind = POPUP_KIND[popup.name]
  if (!kind) return null
  const args = popup.args ?? {}
  let valid = true
  if (kind === 'stock_report') valid = isValidTicker(args.ticker)
  else if (kind === 'manage_watchlist') valid = isValidManage(args)
  return { kind, name: popup.name, args, valid }
}

// popups 배열 → 유효 모달 스펙 리스트(순서 보존, 미지/결측 제외). 비배열 → [].
export function routePopups(popups) {
  if (!Array.isArray(popups)) return []
  return popups.map(routePopup).filter(Boolean)
}
