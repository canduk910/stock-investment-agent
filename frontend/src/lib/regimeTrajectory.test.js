import { describe, it, expect } from 'vitest'
import {
  regimeMarkerPos,
  offsetForVisit,
  trailOpacity,
  buildTrajectory,
} from './regimeTrajectory.js'

describe('regimeMarkerPos (RegimeGauge 마커와 동일 공식 SSOT)', () => {
  it('중립(0,0) = 정중앙(50,50)', () => {
    expect(regimeMarkerPos(0, 0)).toEqual({ x: 50, y: 50 })
  })
  it('경기+2·심리+2 = 우상(88,12)', () => {
    expect(regimeMarkerPos(2, 2)).toEqual({ x: 88, y: 12 })
  })
  it('경기-2·심리-2 = 좌하(12,88)', () => {
    expect(regimeMarkerPos(-2, -2)).toEqual({ x: 12, y: 88 })
  })
  it('null 점수는 0 취급(방어)', () => {
    expect(regimeMarkerPos(null, undefined)).toEqual({ x: 50, y: 50 })
  })
})

describe('offsetForVisit (셀 내 겹침 해소·결정적)', () => {
  it('단일 방문(n<=1)은 오프셋 0', () => {
    expect(offsetForVisit(0, 1)).toEqual({ dx: 0, dy: 0 })
  })
  it('다중 방문은 셀 반폭 내 소반경으로 분산(결정적)', () => {
    const a = offsetForVisit(0, 5)
    const b = offsetForVisit(1, 5)
    expect(a).not.toEqual(b) // 서로 다른 위치로 퍼짐
    for (const o of [a, b]) {
      expect(Math.hypot(o.dx, o.dy)).toBeLessThanOrEqual(6.001) // OFFSET_R 이내
    }
    // 결정적 — 같은 입력은 같은 출력.
    expect(offsetForVisit(1, 5)).toEqual(b)
  })
})

describe('trailOpacity (과거→현재 그라디언트)', () => {
  it('마지막(현재)이 가장 진하고 첫(과거)이 가장 옅다', () => {
    expect(trailOpacity(0, 4)).toBeLessThan(trailOpacity(3, 4))
    expect(trailOpacity(3, 4)).toBeCloseTo(0.9, 5)
  })
  it('단일 점은 불투명', () => {
    expect(trailOpacity(0, 1)).toBe(1)
  })
})

describe('buildTrajectory', () => {
  const RAW = [
    { date: '2024-01-01', cycle_score: 2, sentiment_score: 2, regime: '확장', recommended_cash_ratio: 60 },
    { date: '2024-02-01', cycle_score: 2, sentiment_score: 2, regime: '확장', recommended_cash_ratio: 60 },
    { date: '2024-03-01', cycle_score: -2, sentiment_score: -2, regime: '수축', recommended_cash_ratio: 20 },
  ]

  it('pathD 는 M 로 시작하고 이후 L 세그먼트', () => {
    const { pathD } = buildTrajectory(RAW)
    expect(pathD.startsWith('M')).toBe(true)
    expect((pathD.match(/L/g) || []).length).toBe(2) // 3점 → M + L + L
  })

  it('마지막 점 isLast, 국면 바뀐 지점 isTransition', () => {
    const { points } = buildTrajectory(RAW)
    expect(points).toHaveLength(3)
    expect(points[2].isLast).toBe(true)
    expect(points[0].isLast).toBe(false)
    expect(points[1].isTransition).toBe(false) // 확장→확장
    expect(points[2].isTransition).toBe(true) // 확장→수축
  })

  it('같은 셀의 연속 방문은 오프셋으로 좌표가 갈라진다(겹침 해소)', () => {
    const { points } = buildTrajectory(RAW)
    // 1·2월 모두 (2,2) 셀이지만 좌표가 달라야(오프셋).
    expect(points[0].x !== points[1].x || points[0].y !== points[1].y).toBe(true)
  })

  it('빈 입력은 안전하게 빈 궤적', () => {
    expect(buildTrajectory([])).toEqual({ points: [], pathD: '' })
    expect(buildTrajectory(null)).toEqual({ points: [], pathD: '' })
  })
})
