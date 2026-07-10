import { describe, it, expect } from 'vitest'
import { opinionTone, OPINION_LABELS, historyDeltas } from './reportFormat.js'

// 계약 근거(week-10 계획 P2): 종합의견 배지 색 매핑 — 긍정적=파랑/중립=회색/신중=주황.
//   Pydantic StockReport 종합의견 Literal["긍정적","중립","신중"](llm-engineer SSOT)만 유효.
//   매수·매도 등 명령형 라벨은 스키마가 원천 배제 → 프론트도 알 수 없는 값은 중립 톤으로 방어.

describe('opinionTone — 종합의견 → 배지 톤(색은 컴포넌트가 토큰으로 매핑)', () => {
  it('긍정적 → up(파랑)', () => {
    expect(opinionTone('긍정적')).toBe('up')
  })
  it('중립 → muted(회색)', () => {
    expect(opinionTone('중립')).toBe('muted')
  })
  it('신중 → emph(주황=강조, 위험 아님 → 빨강 아님)', () => {
    expect(opinionTone('신중')).toBe('emph')
  })
  it('알 수 없는/결측 값은 muted 로 방어(임의 색 금지)', () => {
    expect(opinionTone('매수')).toBe('muted')
    expect(opinionTone(null)).toBe('muted')
    expect(opinionTone(undefined)).toBe('muted')
    expect(opinionTone('')).toBe('muted')
  })
})

describe('OPINION_LABELS — 유효 종합의견 3종(스키마 Literal 과 일치)', () => {
  it('긍정적·중립·신중 3종만 정의', () => {
    expect(Object.keys(OPINION_LABELS).sort()).toEqual(['긍정적', '신중', '중립'])
  })
})

describe('historyDeltas — 과거 대비 변화 마커(최신 우선 히스토리, IMP-16)', () => {
  const mk = (opinion, regime) => ({
    report_json: { 종합의견: opinion },
    regime_at_creation: regime,
  })

  it('직전(더 오래된) 대비 종합의견·국면 변화 감지', () => {
    // 최신 우선: [신중/수축, 중립/확장, 중립/확장]
    const d = historyDeltas([mk('신중', '수축'), mk('중립', '확장'), mk('중립', '확장')])
    expect(d[0].opinionChanged).toBe(true) // 중립→신중
    expect(d[0].regimeChanged).toBe(true) // 확장→수축
    expect(d[0].prevOpinion).toBe('중립')
    expect(d[0].prevRegime).toBe('확장')
    expect(d[1].opinionChanged).toBe(false) // 중립==중립
    expect(d[1].regimeChanged).toBe(false)
    expect(d[2].opinionChanged).toBe(false) // 가장 오래된 — 비교 대상 없음
    expect(d[2].regimeChanged).toBe(false)
  })

  it('단일 항목은 변화 없음(비교 대상 없음)', () => {
    const d = historyDeltas([mk('중립', '확장')])
    expect(d[0].opinionChanged).toBe(false)
    expect(d[0].regimeChanged).toBe(false)
  })

  it('비배열 → [](방어)', () => {
    expect(historyDeltas(null)).toEqual([])
    expect(historyDeltas(undefined)).toEqual([])
  })
})
