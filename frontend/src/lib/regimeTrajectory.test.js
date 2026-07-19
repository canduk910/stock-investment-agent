import { describe, it, expect } from 'vitest'
import {
  regimeMarkerPos,
  buildRegimePath,
  stopLabelGroups,
  labelYearShades,
  LABEL_SHADE_LEVELS,
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

describe('labelYearShades (년도별 밝기 그라데이션 — 과거 옅게→최근 짙게)', () => {
  const G = (year, month) => ({ x: 1, y: 1, startDates: [`${year}-${month}-01`] })
  const maxLevel = LABEL_SHADE_LEVELS - 1

  it('서로 다른 연도 → 오래=레벨0, 최근=최대레벨, 단조 증가', () => {
    const out = labelYearShades([G('2024', '03'), G('2025', '06'), G('2026', '01')])
    expect(out.map((g) => g.year)).toEqual(['2024', '2025', '2026'])
    expect(out[0].shadeLevel).toBe(0) // 가장 과거 연도 = 가장 옅게
    expect(out[2].shadeLevel).toBe(maxLevel) // 가장 최근 연도 = 가장 짙게
    expect(out[0].shadeLevel).toBeLessThan(out[1].shadeLevel)
    expect(out[1].shadeLevel).toBeLessThan(out[2].shadeLevel)
  })

  it('두 연도 → 옅음(0)·짙음(최대) 두 단계로 뚜렷', () => {
    const out = labelYearShades([G('2025', '11'), G('2026', '02')])
    expect(out[0].shadeLevel).toBe(0)
    expect(out[1].shadeLevel).toBe(maxLevel)
  })

  it('같은 연도의 라벨은 같은 짙기(월별로 흩지 않음 = 년도별)', () => {
    const out = labelYearShades([G('2025', '01'), G('2025', '09'), G('2026', '03')])
    expect(out[0].shadeLevel).toBe(out[1].shadeLevel) // 2025 두 라벨 동일
    expect(out[2].shadeLevel).toBeGreaterThan(out[0].shadeLevel) // 2026 은 더 짙게
  })

  it('단일 연도(대비 없음) → 전부 레벨0(현 회색 유지·무해)', () => {
    const out = labelYearShades([G('2026', '01'), G('2026', '05')])
    expect(out.every((g) => g.shadeLevel === 0)).toBe(true)
  })

  it('재방문 셀이 여러 해에 걸치면 대표 연도 = 가장 최근 해', () => {
    const out = labelYearShades([
      { x: 1, y: 1, startDates: ['2024-12-01', '2026-01-01'] }, // 재방문(24·26)
      { x: 2, y: 2, startDates: ['2025-06-01'] },
    ])
    expect(out[0].year).toBe('2026') // 최근 해로 대표
    expect(out[0].shadeLevel).toBe(maxLevel) // 2026 = 최근 → 최대 짙기
  })

  it('연도 불명(잘못된 날짜)·빈 입력은 graceful', () => {
    expect(labelYearShades([])).toEqual([])
    expect(labelYearShades(null)).toEqual([])
    const bad = labelYearShades([{ x: 1, y: 1, startDates: [] }])
    expect(bad[0].year).toBeNull()
    expect(bad[0].shadeLevel).toBe(0) // 불명 → 옅게(무해)
  })
})
