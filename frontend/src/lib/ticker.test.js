import { describe, it, expect } from 'vitest'
import { isValidTicker } from './ticker.js'

// 종목코드 유효성 SSOT — 직접입력(StockReport.onSubmit)과 팝업 라우팅(popupRouter)이 공유하는 단일 규칙.
// 규칙 = `[0-9A-Za-z]{6}`(6자 영숫자, 기존 StockReport 직접입력 규칙에 통일). 목적은 numeric 강제가 아니라
// "명백한 불량(종목명·부분입력) 차단" — 직접입력이 받는 코드를 팝업이 거부하면 UX 가 어긋나므로 규칙을 하나로.
describe('isValidTicker — 6자 영숫자 종목코드 형식 게이트(SSOT)', () => {
  it('정확히 6자 숫자면 true', () => {
    expect(isValidTicker('005930')).toBe(true)
    expect(isValidTicker('373220')).toBe(true)
  })
  it('영문 포함 6자도 true(직접입력 규칙과 통일 — 알파벳 코드 거부 금지)', () => {
    expect(isValidTicker('00593A')).toBe(true)
    expect(isValidTicker('A12345')).toBe(true)
  })
  it('자릿수 불량(4자·7자)이면 false', () => {
    expect(isValidTicker('5930')).toBe(false)
    expect(isValidTicker('0059300')).toBe(false)
  })
  it('한글(종목명)·공백·특수문자면 false(명백한 불량 차단)', () => {
    expect(isValidTicker('삼성전자')).toBe(false)
    expect(isValidTicker('005 30')).toBe(false)
    expect(isValidTicker('005-30')).toBe(false)
  })
  it('결측·비문자열이면 false', () => {
    expect(isValidTicker(null)).toBe(false)
    expect(isValidTicker(undefined)).toBe(false)
    expect(isValidTicker(5930)).toBe(false)
    expect(isValidTicker('')).toBe(false)
  })
})
