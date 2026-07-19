import { describe, it, expect } from 'vitest'
import { regimeMarkerPos, buildRegimePath, stopLabelGroups } from './regimeTrajectory.js'

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

describe('buildRegimePath (단순 경로 — 인접 동일 셀 접기)', () => {
  const P = (date, cs, ss, regime) => ({ date, cycle_score: cs, sentiment_score: ss, regime })

  it('인접 동일 셀은 한 정차점으로 접고 dwell 누적', () => {
    const { stops } = buildRegimePath([
      P('2024-01-01', 2, 2, '확장'),
      P('2024-02-01', 2, 2, '확장'), // 같은 셀 → 접힘
      P('2024-03-01', -2, -2, '수축'),
    ])
    expect(stops).toHaveLength(2) // 3개월 → 2 정차점
    expect(stops[0]).toMatchObject({
      cs: 2, ss: 2, dwell: 2, startDate: '2024-01-01', endDate: '2024-02-01', isFirst: true,
    })
    expect(stops[1]).toMatchObject({ cs: -2, ss: -2, dwell: 1, isLast: true })
  })

  it('서로 다른 셀은 각각 정차점, 재방문도 새 정차점', () => {
    const { stops } = buildRegimePath([
      P('2024-01-01', 2, 2, '확장'),
      P('2024-02-01', -2, -2, '수축'),
      P('2024-03-01', 2, 2, '확장'), // 재방문 → 새 정차점
    ])
    expect(stops).toHaveLength(3)
    expect(stops.map((s) => s.cs)).toEqual([2, -2, 2])
  })

  it('pathD 는 M 시작·정차점마다 L, 과거→현재 opacity 증가', () => {
    const { stops, pathD } = buildRegimePath([
      P('2024-01-01', 2, 2, '확장'),
      P('2024-02-01', 0, 0, '확장'),
      P('2024-03-01', -2, -2, '수축'),
    ])
    expect(pathD.startsWith('M')).toBe(true)
    expect((pathD.match(/L/g) || []).length).toBe(2) // 3 정차점 → M + L + L
    expect(stops[0].opacity).toBeLessThan(stops[2].opacity)
    expect(stops[2].opacity).toBeCloseTo(1, 5)
  })

  it('좌표는 셀 중심(오프셋 없음) — 같은 셀 재방문은 동일 좌표(깔끔)', () => {
    const { stops } = buildRegimePath([
      P('2024-01-01', 2, 2, '확장'),
      P('2024-02-01', -2, -2, '수축'),
      P('2024-03-01', 2, 2, '확장'),
    ])
    expect(stops[0].x).toBe(stops[2].x)
    expect(stops[0].y).toBe(stops[2].y)
  })

  it('빈 입력은 안전', () => {
    expect(buildRegimePath([])).toEqual({ stops: [], pathD: '' })
    expect(buildRegimePath(null)).toEqual({ stops: [], pathD: '' })
  })

  it('단일 정차점은 opacity 1·pathD 는 M 만(선 없음)', () => {
    const { stops, pathD } = buildRegimePath([P('2024-01-01', 1, 1, '확장')])
    expect(stops).toHaveLength(1)
    expect(stops[0].opacity).toBe(1)
    expect(pathD.startsWith('M') && !pathD.includes('L')).toBe(true)
  })
})

describe('stopLabelGroups (재방문 좌표 라벨 병합 — 겹침 방지)', () => {
  const P = (date, cs, ss, regime) => ({ date, cycle_score: cs, sentiment_score: ss, regime })

  it('같은 좌표(재방문) 정차점의 시작월을 한 그룹으로 모은다', () => {
    const { stops } = buildRegimePath([
      P('2024-01-01', 2, 2, '확장'),
      P('2024-02-01', -2, -2, '수축'),
      P('2024-03-01', 2, 2, '확장'), // 확장 재방문 → 확장 좌표에 2개
    ])
    const groups = stopLabelGroups(stops)
    expect(groups).toHaveLength(2) // 확장 좌표 1 + 수축 좌표 1
    const exp = groups.find((g) => g.x === stops[0].x && g.y === stops[0].y)
    expect(exp.startDates).toEqual(['2024-01-01', '2024-03-01']) // 두 방문 병합(시간순)
    const con = groups.find((g) => g !== exp)
    expect(con.startDates).toEqual(['2024-02-01'])
  })

  it('빈 입력은 안전', () => {
    expect(stopLabelGroups([])).toEqual([])
    expect(stopLabelGroups(null)).toEqual([])
  })
})
