import { describe, it, expect } from 'vitest'
import {
  grandCycleStages,
  stageGlyph,
  bandReadout,
  grandCycleInsight,
} from './grandCycle.js'

// 고지로 이동평균선 대순환 표현 로직(순수) — 브라우저 없이 검증. 판정(단계·밴드)은 백엔드가,
// 여기서는 그 결과를 "어떻게 표시할지"만(서술·글리프·라벨). 매매 판단·수익 보장 표현 금지.

const CATALOG = {
  periods: { short: 5, medium: 20, long: 40 },
  stages: [
    { stage: 1, name: '안정 상승기', arrangement: '단 > 중 > 장', phase: '상승' },
    { stage: 2, name: '상승 둔화기', arrangement: '중 > 단 > 장', phase: '상승' },
    { stage: 3, name: '하락 진입기', arrangement: '중 > 장 > 단', phase: '전환' },
    { stage: 4, name: '안정 하락기', arrangement: '장 > 중 > 단', phase: '하락' },
    { stage: 5, name: '하락 둔화기', arrangement: '장 > 단 > 중', phase: '하락' },
    { stage: 6, name: '상승 진입기', arrangement: '단 > 장 > 중', phase: '전환' },
  ],
}

const GC = {
  stage: 1,
  stage_name: '안정 상승기',
  arrangement: '단 > 중 > 장',
  phase: '상승',
  ma: { short: 190, medium: 152.5, long: 126.25 },
  periods: { short: 5, medium: 20, long: 40 },
  band_width_pct: 3.24,
  band_direction: '확대',
  bars_in_stage: 12,
  prev_stage: null,
}

describe('grandCycleStages', () => {
  it('카탈로그 6단계 + 현재 단계만 isCurrent', () => {
    const list = grandCycleStages(CATALOG, 1)
    expect(list).toHaveLength(6)
    expect(list[0].isCurrent).toBe(true)
    expect(list[1].isCurrent).toBe(false)
    expect(list[3].name).toBe('안정 하락기')
  })

  it('카탈로그 없음/빈 stages → 빈 배열(graceful)', () => {
    expect(grandCycleStages(null, 1)).toEqual([])
    expect(grandCycleStages({ stages: [] }, 1)).toEqual([])
    expect(grandCycleStages({}, 1)).toEqual([])
  })

  it('현재 단계 null(동률·미판정)이면 isCurrent 전부 false', () => {
    const list = grandCycleStages(CATALOG, null)
    expect(list.every((s) => s.isCurrent === false)).toBe(true)
  })
})

describe('stageGlyph', () => {
  it('국면별 방향 글리프(색 아닌 형태로 방향 표기)', () => {
    expect(stageGlyph('상승')).toBe('▲')
    expect(stageGlyph('하락')).toBe('▼')
    expect(stageGlyph('전환')).toBe('◆')
    expect(stageGlyph('없는국면')).toBe('─')
    expect(stageGlyph(null)).toBe('─')
  })
})

describe('bandReadout', () => {
  it('밴드폭(부호) + 방향', () => {
    expect(bandReadout(GC)).toBe('+3.24% · 확대')
    expect(bandReadout({ band_width_pct: -2.5, band_direction: '축소' })).toBe('-2.50% · 축소')
  })

  it('방향 없으면 폭만', () => {
    expect(bandReadout({ band_width_pct: 1.1, band_direction: null })).toBe('+1.10%')
  })

  it('밴드 결측 → —', () => {
    expect(bandReadout({ band_width_pct: null })).toBe('—')
    expect(bandReadout(null)).toBe('—')
  })
})

describe('grandCycleInsight', () => {
  it('단계·밴드·지속·국면을 방법론 인용으로 서술(매매 지시 아님)', () => {
    const s = grandCycleInsight(GC)
    expect(s).toContain('1단계')
    expect(s).toContain('안정 상승기')
    expect(s).toContain('12봉')
    expect(s).toContain('상승')
    // 단정적 매매 지시·수익 보장 표현이 없어야 한다.
    expect(s).not.toMatch(/사세요|파세요|매수하세요|매도하세요|보장/)
  })

  it('직전 단계가 있으면 전환 언급', () => {
    const s = grandCycleInsight({ ...GC, prev_stage: 6 })
    expect(s).toContain('전환')
    expect(s).toContain('6단계')
  })

  it('null/미판정 graceful', () => {
    expect(grandCycleInsight(null)).toBe('')
    expect(grandCycleInsight({ ...GC, stage: null })).toContain('보류')
  })
})
