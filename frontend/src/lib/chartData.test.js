import { describe, it, expect } from 'vitest'
import { dateToTimestamp, candlesToKline } from './chartData.js'

// 계약 근거: 계획 "가격 차트" — bundle chart.candles[{date:'YYYYMMDD',open,high,low,close,volume}]
//   → klinecharts {timestamp(ms), open, high, low, close, volume}. date→epoch 변환.

describe('dateToTimestamp — YYYYMMDD → epoch ms', () => {
  it('YYYYMMDD 를 UTC 자정 epoch(ms)로 변환한다(결정적, 로컬 타임존 무관)', () => {
    expect(dateToTimestamp('20260705')).toBe(Date.UTC(2026, 6, 5))
  })

  it('연/월/일 경계를 올바르게 파싱한다', () => {
    expect(dateToTimestamp('20240101')).toBe(Date.UTC(2024, 0, 1))
    expect(dateToTimestamp('20231231')).toBe(Date.UTC(2023, 11, 31))
  })

  it('이미 8자리 숫자여도 문자열로 처리한다', () => {
    expect(dateToTimestamp(20260705)).toBe(Date.UTC(2026, 6, 5))
  })

  it('형식이 잘못되면 null(임의 날짜로 렌더 금지)', () => {
    expect(dateToTimestamp('2026-07-05')).toBeNull()
    expect(dateToTimestamp('bad')).toBeNull()
    expect(dateToTimestamp('')).toBeNull()
    expect(dateToTimestamp(null)).toBeNull()
    expect(dateToTimestamp(undefined)).toBeNull()
  })
})

describe('candlesToKline — 번들 캔들 → klinecharts KLineData', () => {
  const raw = [
    { date: '20260703', open: 100, high: 110, low: 95, close: 105, volume: 1000 },
    { date: '20260701', open: 90, high: 95, low: 88, close: 92, volume: 800 },
    { date: '20260702', open: 92, high: 100, low: 91, close: 99, volume: 900 },
  ]

  it('각 캔들을 timestamp/open/high/low/close/volume 로 매핑한다', () => {
    const out = candlesToKline(raw)
    expect(out[0]).toEqual({
      timestamp: Date.UTC(2026, 6, 1),
      open: 90,
      high: 95,
      low: 88,
      close: 92,
      volume: 800,
    })
  })

  it('timestamp 오름차순으로 정렬한다(klinecharts 요건)', () => {
    const ts = candlesToKline(raw).map((c) => c.timestamp)
    expect(ts).toEqual([...ts].sort((a, b) => a - b))
    expect(ts).toEqual([Date.UTC(2026, 6, 1), Date.UTC(2026, 6, 2), Date.UTC(2026, 6, 3)])
  })

  it('문자열 숫자(콤마 없는)를 number 로 강제 변환한다', () => {
    const out = candlesToKline([
      { date: '20260701', open: '90', high: '95', low: '88', close: '92', volume: '800' },
    ])
    expect(out[0].open).toBe(90)
    expect(out[0].volume).toBe(800)
    expect(typeof out[0].close).toBe('number')
  })

  it('날짜가 파싱 불가하거나 OHLC 결측인 행은 조용히 제외한다(임의값 주입 금지)', () => {
    const out = candlesToKline([
      { date: 'bad', open: 1, high: 2, low: 0.5, close: 1.5, volume: 1 },
      { date: '20260701', open: 90, high: 95, low: 88, close: null, volume: 800 },
      { date: '20260702', open: 92, high: 100, low: 91, close: 99, volume: 900 },
    ])
    expect(out).toHaveLength(1)
    expect(out[0].timestamp).toBe(Date.UTC(2026, 6, 2))
  })

  it('volume 결측은 0 으로 채우되 OHLC 는 결측 시 제외한다', () => {
    const out = candlesToKline([
      { date: '20260701', open: 90, high: 95, low: 88, close: 92 },
    ])
    expect(out[0].volume).toBe(0)
  })

  it('빈/비배열 입력은 빈 배열', () => {
    expect(candlesToKline([])).toEqual([])
    expect(candlesToKline(null)).toEqual([])
    expect(candlesToKline(undefined)).toEqual([])
  })
})
