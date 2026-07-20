import { describe, it, expect } from 'vitest'
import {
  regimeMarkerPos,
  buildSampledTrajectory,
  labelYearShades,
  placeLabelY,
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

describe('buildSampledTrajectory (표본별 개별 노드 — 같은 칸 반복 오프셋)', () => {
  const P = (date, cs, ss, regime) => ({ date, cycle_score: cs, sentiment_score: ss, regime })

  it('서로 다른 칸 표본은 각각 노드(병합 안 함)·경로 M+L…·과거→최근 opacity 증가', () => {
    const { nodes, visible, pathD } = buildSampledTrajectory([
      P('2024-01-01', 2, 2, '확장'),
      P('2024-02-01', 0, 0, '확장'),
      P('2024-03-01', -2, -2, '수축'),
    ])
    expect(nodes).toHaveLength(3)
    expect(visible).toHaveLength(3) // 병합 없이 각 표본 개별
    expect(pathD.startsWith('M')).toBe(true)
    expect((pathD.match(/L/g) || []).length).toBe(2) // 3 노드 → M+L+L
    expect(nodes[0].opacity).toBeLessThan(nodes[2].opacity)
    expect(nodes[2].opacity).toBeCloseTo(1, 5)
    expect(nodes[2].isLast).toBe(true)
  })

  it('같은 칸 반복(같은 cs,ss) 표본은 병합 없이 대각 오프셋으로 분리', () => {
    const { nodes } = buildSampledTrajectory([
      P('2024-01-01', 2, 2, '확장'),
      P('2024-04-01', 2, 2, '확장'), // 같은 칸 재방문
    ])
    expect(nodes).toHaveLength(2)
    expect(nodes[0].baseX).toBe(nodes[1].baseX) // 기본 좌표는 같지만
    expect(nodes[0].baseY).toBe(nodes[1].baseY)
    expect(nodes[0].x).toBe(nodes[0].baseX) // 첫 점은 기준(오프셋 0)
    expect(nodes[1].x).not.toBe(nodes[0].x) // 둘째는 오프셋 → 표시 좌표 달라짐(개별 점)
  })

  it('가장 최근 표본이 라이브 칸이면 defer(노드 생략)·경로는 라이브로 종결', () => {
    const live = regimeMarkerPos(2, 0)
    const { nodes, visible, pathD, deferLast } = buildSampledTrajectory(
      [P('2024-01-01', -2, -2, '수축'), P('2024-06-01', 2, 0, '확장')],
      live,
    )
    expect(deferLast).toBe(true)
    expect(nodes[1].deferToLive).toBe(true)
    expect(visible).toHaveLength(1) // 최근 표본은 라이브 마커가 대표
    expect(pathD.trim().endsWith(`${live.x.toFixed(2)} ${live.y.toFixed(2)}`)).toBe(true)
  })

  it('과거 표본이 라이브 칸이면 오프셋으로 라이브 마커와 안 겹침(라벨 억제 버그 방지)', () => {
    const live = regimeMarkerPos(2, 0)
    const { nodes, visible } = buildSampledTrajectory(
      [
        P('2024-01-01', 2, 0, '확장'), // 과거인데 라이브 칸
        P('2024-06-01', -2, -2, '수축'), // 최근(라이브 칸 아님)
      ],
      live,
    )
    expect(nodes[1].deferToLive).toBe(false) // 최근이 라이브 칸 아님 → defer 없음
    expect(visible).toHaveLength(2)
    expect(nodes[0].x !== live.x || nodes[0].y !== live.y).toBe(true) // 라이브와 다른 표시 좌표
  })

  it('라이브 없으면 defer 없음·모든 표본 노드·마지막 isLast', () => {
    const { visible, deferLast, nodes } = buildSampledTrajectory([
      P('2024-01-01', 2, 2, '확장'),
      P('2024-02-01', -2, -2, '수축'),
    ])
    expect(deferLast).toBe(false)
    expect(visible).toHaveLength(2)
    expect(nodes[1].isLast).toBe(true)
  })

  it('빈 입력은 안전', () => {
    const empty = { nodes: [], visible: [], pathD: '', deferLast: false }
    expect(buildSampledTrajectory([])).toEqual(empty)
    expect(buildSampledTrajectory(null)).toEqual(empty)
  })
})

describe('placeLabelY (라벨 세로 위치 — 상/하단 pole 라벨 회피 뒤집기)', () => {
  it('상단 점(경기 양호 근처, y<20)은 라벨을 점 아래로(축 pole 라벨 회피)', () => {
    expect(placeLabelY(12, 3.6, 5.4)).toBeCloseTo(17.4, 5) // 위(8.4)가 아니라 아래
    expect(placeLabelY(12, 3.6, 5.4)).toBeGreaterThan(12) // 점보다 아래
  })
  it('하단 점(경기 악화 근처, y>80)은 라벨을 점 위로', () => {
    expect(placeLabelY(88, 3.6, 5.4)).toBeCloseTo(84.4, 5)
    expect(placeLabelY(88, 3.6, 5.4)).toBeLessThan(88)
  })
  it('중간대는 위/아래 절반 규칙 유지(상단 절반=위·하단 절반=아래)', () => {
    expect(placeLabelY(31, 3.6, 5.4)).toBeCloseTo(27.4, 5) // 상단 절반 → 위
    expect(placeLabelY(60, 3.6, 5.4)).toBeCloseTo(65.4, 5) // 하단 절반 → 아래
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
