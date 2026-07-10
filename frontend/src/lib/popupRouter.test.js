import { describe, it, expect } from 'vitest'
import { routePopup, routePopups, POPUP_KIND } from './popupRouter.js'

// 계약 근거(승인 계획 §프론트엔드 · Task #8): chat 응답 = {text, popups:[{name, args}]}.
// popups[].name(3종) → 컴포넌트 분기. 팝업 실데이터는 프론트가 API로 직접 조회하므로
// 라우팅 순수함수는 "무엇을 열지(kind)와 인자(args)"만 결정한다(데이터는 컴포넌트가 조회).
//   show_stock_report   → StockReportView 모달(args.ticker 로 fetchStockBundle)
//   show_macro_dashboard → RegimeGauge 모달(fetchMacroRegime, 자체 조회)
//   show_watchlist       → W10 플레이스홀더
// 라우팅은 name 으로만 분기(enum 인자는 통과시켜 컴포넌트가 해석). 미지의 name 은 조용히 제외(크래시 금지).

describe('routePopup — 단일 팝업 툴 이름 → 컴포넌트 kind 분기', () => {
  it('show_stock_report(정상 6자리 ticker) → kind stock_report + args 보존 + valid true', () => {
    const r = routePopup({ name: 'show_stock_report', args: { ticker: '005930', focus: 'both' } })
    expect(r.kind).toBe('stock_report')
    expect(r.args.ticker).toBe('005930')
    expect(r.args.focus).toBe('both')
    expect(r.valid).toBe(true)
  })

  it('show_macro_dashboard → kind macro_dashboard + valid true(ticker 무관)', () => {
    const r = routePopup({ name: 'show_macro_dashboard', args: { highlight: 'cash_ratio' } })
    expect(r.kind).toBe('macro_dashboard')
    expect(r.args.highlight).toBe('cash_ratio')
    expect(r.valid).toBe(true)
  })

  it('show_watchlist → kind watchlist + valid true(ticker 무관)', () => {
    const r = routePopup({ name: 'show_watchlist', args: { sort_by: 'change_rate' } })
    expect(r.kind).toBe('watchlist')
    expect(r.valid).toBe(true)
  })

  it('args 누락 시 빈 객체로 기본값(undefined 접근 방지)', () => {
    const r = routePopup({ name: 'show_macro_dashboard' })
    expect(r.args).toEqual({})
  })

  it('미지의 name → null(조용히 무시, 임의 컴포넌트 렌더 금지)', () => {
    expect(routePopup({ name: 'show_unknown', args: {} })).toBeNull()
    expect(routePopup({ name: 'order_stock', args: {} })).toBeNull()
  })

  it('name 결측/비객체 → null(방어)', () => {
    expect(routePopup(null)).toBeNull()
    expect(routePopup({})).toBeNull()
    expect(routePopup({ name: 123 })).toBeNull()
  })
})

describe('routePopups — popups 배열 → 모달 스펙 리스트', () => {
  it('유효 팝업들을 순서대로 매핑', () => {
    const specs = routePopups([
      { name: 'show_stock_report', args: { ticker: '005930' } },
      { name: 'show_macro_dashboard', args: {} },
    ])
    expect(specs.map((s) => s.kind)).toEqual(['stock_report', 'macro_dashboard'])
  })

  it('미지의 name 은 걸러내고 유효한 것만(부분 실패 대신 조용히 제외)', () => {
    const specs = routePopups([
      { name: 'show_watchlist', args: {} },
      { name: 'nope', args: {} },
    ])
    expect(specs).toHaveLength(1)
    expect(specs[0].kind).toBe('watchlist')
  })

  it('비배열/결측 → 빈 배열(팝업 없음)', () => {
    expect(routePopups(null)).toEqual([])
    expect(routePopups(undefined)).toEqual([])
    expect(routePopups({})).toEqual([])
  })

  it('빈 배열(팝업 없는 텍스트-only 응답·risk_guardrail 차단) → 빈 배열', () => {
    expect(routePopups([])).toEqual([])
  })
})

// 계약 근거(QA 관찰·team-lead): show_stock_report.ticker 는 스키마 pattern 강제가 없어 LLM 환각으로
// 형식 불량 ticker 가 올 수 있다. 라우팅 단계에서 isValidTicker(SSOT, ticker.js)로 검증해 valid=false 로
// 표시하고(조회 금지) 컴포넌트가 graceful 안내하게 한다. 형식 규칙 자체의 케이스는 ticker.test.js 에서 검증.
describe('routePopup — show_stock_report ticker 형식 가드(isValidTicker 공유)', () => {
  it('유효 코드(영숫자 6자) → valid true', () => {
    expect(routePopup({ name: 'show_stock_report', args: { ticker: '005930' } }).valid).toBe(true)
    expect(routePopup({ name: 'show_stock_report', args: { ticker: '00593A' } }).valid).toBe(true)
  })
  it('형식 불량 ticker(종목명·짧은 숫자) → kind 는 유지하되 valid false(fetch 금지 신호)', () => {
    expect(routePopup({ name: 'show_stock_report', args: { ticker: '삼성전자' } }).valid).toBe(false)
    expect(routePopup({ name: 'show_stock_report', args: { ticker: '5930' } }).valid).toBe(false)
  })
  it('ticker 결측 → valid false(조회하지 않고 안내)', () => {
    const r = routePopup({ name: 'show_stock_report', args: {} })
    expect(r.kind).toBe('stock_report')
    expect(r.valid).toBe(false)
  })
})

describe('routePopup — manage_watchlist(IMP-08: 편집 확인 팝업)', () => {
  it('add + 유효 ticker → kind manage_watchlist, valid true', () => {
    const s = routePopup({ name: 'manage_watchlist', args: { action: 'add', ticker: '005930' } })
    expect(s.kind).toBe('manage_watchlist')
    expect(s.valid).toBe(true)
  })
  it('remove + 유효 ticker → valid', () => {
    expect(
      routePopup({ name: 'manage_watchlist', args: { action: 'remove', ticker: '005930' } }).valid,
    ).toBe(true)
  })
  it('set_target + target_price(>=0) → valid', () => {
    expect(
      routePopup({
        name: 'manage_watchlist',
        args: { action: 'set_target', ticker: '005930', target_price: 80000 },
      }).valid,
    ).toBe(true)
  })
  it('set_target 인데 target_price 결측/음수 → valid false', () => {
    expect(
      routePopup({ name: 'manage_watchlist', args: { action: 'set_target', ticker: '005930' } })
        .valid,
    ).toBe(false)
    expect(
      routePopup({
        name: 'manage_watchlist',
        args: { action: 'set_target', ticker: '005930', target_price: -1 },
      }).valid,
    ).toBe(false)
  })
  it('알 수 없는 action(예: buy) → valid false(자동 매매 아님)', () => {
    expect(
      routePopup({ name: 'manage_watchlist', args: { action: 'buy', ticker: '005930' } }).valid,
    ).toBe(false)
  })
  it('불량 ticker → valid false', () => {
    expect(
      routePopup({ name: 'manage_watchlist', args: { action: 'add', ticker: '삼성' } }).valid,
    ).toBe(false)
  })
})

describe('POPUP_KIND — 라우팅 계약 상수(4종)', () => {
  it('정확히 4종 툴 이름만 매핑(오발동 방지)', () => {
    expect(Object.keys(POPUP_KIND).sort()).toEqual([
      'manage_watchlist',
      'show_macro_dashboard',
      'show_stock_report',
      'show_watchlist',
    ])
  })
})
