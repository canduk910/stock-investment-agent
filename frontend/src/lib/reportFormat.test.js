import { describe, it, expect } from 'vitest'
import { opinionTone, OPINION_LABELS } from './reportFormat.js'

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
