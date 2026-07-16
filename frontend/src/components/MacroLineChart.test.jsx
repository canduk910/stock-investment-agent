import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import MacroLineChart from './MacroLineChart.jsx'

// 월단위 라인차트 — 남색 선 + 회색 임계 점선 + 주황 현재값. 2점 미만은 렌더 생략.

const POINTS = [
  { date: '2025-10-01', value: 16 },
  { date: '2025-11-01', value: 22 },
  { date: '2025-12-01', value: 30 },
]

describe('MacroLineChart', () => {
  it('2점 이상 → SVG 라인(path) 렌더', () => {
    const { container } = render(<MacroLineChart points={POINTS} unit="" thresholds={{ lo: 14, hi: 28 }} />)
    expect(container.querySelector('svg.macro-chart')).toBeTruthy()
    expect(container.querySelector('path.macro-chart__line')).toBeTruthy()
  })

  it('임계 가이드라인(lo/hi) 2개 렌더 — 구간 경계 시각화', () => {
    const { container } = render(<MacroLineChart points={POINTS} thresholds={{ lo: 14, hi: 28 }} />)
    expect(container.querySelectorAll('line.macro-chart__guide').length).toBe(2)
  })

  it('현재값(마지막 포인트) 강조 마커', () => {
    const { container } = render(<MacroLineChart points={POINTS} thresholds={{ lo: 14, hi: 28 }} />)
    expect(container.querySelector('circle.macro-chart__last-dot')).toBeTruthy()
  })

  it('2점 미만·비배열은 렌더 안 함(null)', () => {
    expect(render(<MacroLineChart points={[{ date: '2025-12-01', value: 3 }]} />).container.querySelector('svg')).toBeFalsy()
    expect(render(<MacroLineChart points={null} />).container.querySelector('svg')).toBeFalsy()
  })

  it('임계 없으면 가이드라인 없이도 렌더', () => {
    const { container } = render(<MacroLineChart points={POINTS} />)
    expect(container.querySelector('path.macro-chart__line')).toBeTruthy()
    expect(container.querySelectorAll('line.macro-chart__guide').length).toBe(0)
  })

  it('전 구간 동일 값(도메인 붕괴 가드) → 크래시·NaN 없이 라인 렌더', () => {
    const flat = [
      { date: '2025-10-01', value: 20 },
      { date: '2025-11-01', value: 20 },
      { date: '2025-12-01', value: 20 },
    ]
    const { container } = render(<MacroLineChart points={flat} thresholds={{ lo: 14, hi: 28 }} />)
    const d = container.querySelector('path.macro-chart__line')?.getAttribute('d')
    expect(d).toBeTruthy()
    expect(d).not.toContain('NaN') // yMax===yMin 가드로 0-division 없이 정상 좌표
  })
})
