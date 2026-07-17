import { describe, it, expect } from 'vitest'
import { num, won, signedWon, signedPct, signedNum, pct, qty, changeDir, flatDir } from './format.js'

// 각 함수는 기존 컴포넌트 로컬 포맷터의 동작을 그대로 옮긴 것(행동 보존). 특히 % 유무·결측 fallback 차이.

describe('num', () => {
  it('천단위 콤마·자릿수·결측', () => {
    expect(num(1234567)).toBe((1234567).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 }))
    expect(num(12.345, 2)).toBe((12.345).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
    expect(num(null)).toBe('—')
    expect(num('abc')).toBe('—')
  })
})

describe('won / signedWon / qty', () => {
  it('원 단위·부호·수량', () => {
    expect(won(70500)).toBe('70,500원')
    expect(won(null)).toBe('—')
    expect(signedWon(1200)).toBe('+1,200원')
    expect(signedWon(-800)).toBe('-800원')
    expect(signedWon(null)).toBe('—')
    expect(qty(10)).toBe('10')
    expect(qty(null)).toBe('—')
  })
})

describe('signedPct(%) vs signedNum(무%) — 동작 보존', () => {
  it('signedPct 는 % 포함(기본 2자리)', () => {
    expect(signedPct(3.2)).toBe('+3.20%')
    expect(signedPct(-1.5)).toBe('-1.50%')
    expect(signedPct(null)).toBe('—')
  })
  it('signedNum 은 % 없음(기본 2자리)', () => {
    expect(signedNum(3.2)).toBe('+3.20')
    expect(signedNum(-1.5)).toBe('-1.50')
    expect(signedNum(null)).toBe('—')
  })
})

describe('pct', () => {
  it('부호·% 없음(기본 1자리)', () => {
    expect(pct(54.07)).toBe('54.1')
    expect(pct(12.3, 2)).toBe('12.30')
    expect(pct(null)).toBe('—')
  })
})

describe('changeDir(null) vs flatDir(flat) — 결측 처리 보존', () => {
  it('changeDir 는 결측이면 null', () => {
    expect(changeDir(1)).toBe('up')
    expect(changeDir(-1)).toBe('down')
    expect(changeDir(0)).toBe('flat')
    expect(changeDir(null)).toBe(null)
  })
  it('flatDir 는 결측이면 flat', () => {
    expect(flatDir(1)).toBe('up')
    expect(flatDir(-1)).toBe('down')
    expect(flatDir(0)).toBe('flat')
    expect(flatDir(null)).toBe('flat')
  })
})
