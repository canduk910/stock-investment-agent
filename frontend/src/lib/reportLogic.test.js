import { describe, it, expect } from 'vitest'
import { sectionFailed, isValuationReady, yoyChange } from './reportLogic.js'

// 계약 근거: 계획 "번들 계약" partial_failure:[] · summary.avg_per/valuation_label null 게이트 ·
//   FinancialTrendTable YoY ▲▼(파랑/회색만).

describe('sectionFailed — partial_failure 섹션 판정', () => {
  it('문자열 리스트에 섹션이 있으면 true', () => {
    expect(sectionFailed(['financials', 'chart'], 'financials')).toBe(true)
    expect(sectionFailed(['financials'], 'chart')).toBe(false)
  })

  it('객체 리스트({section, reason})도 방어적으로 수용', () => {
    const pf = [{ section: 'chart', reason: 'timeout' }]
    expect(sectionFailed(pf, 'chart')).toBe(true)
    expect(sectionFailed(pf, 'valuation')).toBe(false)
  })

  it('빈/비배열/누락이면 false(정상 렌더)', () => {
    expect(sectionFailed([], 'chart')).toBe(false)
    expect(sectionFailed(null, 'chart')).toBe(false)
    expect(sectionFailed(undefined, 'chart')).toBe(false)
  })
})

describe('isValuationReady — avg_per/valuation_label null 게이트', () => {
  it('avg_per 와 valuation_label 이 모두 있으면 true', () => {
    expect(isValuationReady({ avg_per: 12.3, valuation_label: '적정' })).toBe(true)
  })

  it('avg_per 또는 valuation_label 이 null 이면 false("판정 준비 중")', () => {
    expect(isValuationReady({ avg_per: null, valuation_label: '적정' })).toBe(false)
    expect(isValuationReady({ avg_per: 12.3, valuation_label: null })).toBe(false)
    expect(isValuationReady({ avg_per: null, valuation_label: null })).toBe(false)
  })

  it('summary 자체가 null 이면 false', () => {
    expect(isValuationReady(null)).toBe(false)
    expect(isValuationReady(undefined)).toBe(false)
  })
})

describe('yoyChange — 전기 대비 증감 방향(파랑=증가/회색=감소, 색만으로 구분 금지 → dir 문자열)', () => {
  it('증가면 dir=up + 양수 delta/pct', () => {
    const r = yoyChange(120, 100)
    expect(r.dir).toBe('up')
    expect(r.delta).toBe(20)
    expect(r.pct).toBeCloseTo(20)
  })

  it('감소면 dir=down + 음수 delta', () => {
    const r = yoyChange(80, 100)
    expect(r.dir).toBe('down')
    expect(r.delta).toBe(-20)
    expect(r.pct).toBeCloseTo(-20)
  })

  it('동일하면 dir=flat', () => {
    expect(yoyChange(100, 100).dir).toBe('flat')
  })

  it('전기값이 없거나 0(또는 음수)이면 pct=null(0 나눗셈·부호역전 방지) — dir 은 delta 부호로', () => {
    expect(yoyChange(100, null).pct).toBeNull()
    expect(yoyChange(100, 0).pct).toBeNull()
    const r = yoyChange(100, -50)
    expect(r.pct).toBeNull()
  })

  it('현재값이 결측이면 전부 null(임의 방향 금지)', () => {
    expect(yoyChange(null, 100)).toEqual({ delta: null, pct: null, dir: null })
    expect(yoyChange(undefined, 100)).toEqual({ delta: null, pct: null, dir: null })
  })
})
