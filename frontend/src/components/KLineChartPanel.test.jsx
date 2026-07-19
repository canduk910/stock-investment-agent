import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import KLineChartPanel from './KLineChartPanel.jsx'

// klinecharts 는 canvas 렌더라 jsdom 에서 실제로 못 그린다 → 라이브러리 경계를 mock 하고
// "무엇을 호출했는가"(계약)만 검증한다: MA 지표 5/20/40, 스테이지 리본 오버레이 생성.

const chart = {
  setStyles: vi.fn(),
  createIndicator: vi.fn(),
  createOverlay: vi.fn(),
  removeOverlay: vi.fn(),
  applyNewData: vi.fn(),
  resize: vi.fn(),
}
vi.mock('klinecharts', () => ({
  init: vi.fn(() => chart),
  dispose: vi.fn(),
  registerOverlay: vi.fn(),
}))
import { registerOverlay } from 'klinecharts'

const CANDLES = [
  { date: '20260101', open: 100, high: 110, low: 90, close: 105, volume: 1000 },
  { date: '20260102', open: 105, high: 115, low: 95, close: 110, volume: 1200 },
]
const INDICATOR_CONFIG = {
  ma_period: 20,
  rsi_period: 14,
  grand_cycle: {
    periods: { short: 5, medium: 20, long: 40 },
    stages: [
      { stage: 1, name: '안정 상승기', phase: '상승' },
      { stage: 4, name: '안정 하락기', phase: '하락' },
    ],
  },
}
const SEGMENTS = [
  { stage: 1, start_date: '20260101', end_date: '20260110' },
  { stage: 4, start_date: '20260111', end_date: '20260120' },
]

beforeEach(() => {
  Object.values(chart).forEach((f) => f.mockClear())
  registerOverlay.mockClear()
})

describe('KLineChartPanel', () => {
  it('grand_cycle 기간이 있으면 MA calcParams [5,20,40] 로 지표 생성(3MA)', () => {
    render(<KLineChartPanel candles={CANDLES} indicatorConfig={INDICATOR_CONFIG} valuation={null} />)
    const maCall = chart.createIndicator.mock.calls.find((c) => c[0]?.name === 'MA')
    expect(maCall).toBeTruthy()
    expect(maCall[0].calcParams).toEqual([5, 20, 40])
  })

  it('gcStageBand 템플릿 등록 + 세그먼트마다 timestamp 오버레이 생성(마지막=현재)', () => {
    render(
      <KLineChartPanel
        candles={CANDLES}
        indicatorConfig={INDICATOR_CONFIG}
        valuation={null}
        stageSegments={SEGMENTS}
        currentStage={4}
      />,
    )
    expect(registerOverlay.mock.calls.some((c) => c[0]?.name === 'gcStageBand')).toBe(true)
    const bands = chart.createOverlay.mock.calls.filter((c) => c[0]?.name === 'gcStageBand')
    expect(bands).toHaveLength(2)
    // 첫 세그먼트: 2개 timestamp 포인트(숫자).
    expect(bands[0][0].points).toHaveLength(2)
    expect(typeof bands[0][0].points[0].timestamp).toBe('number')
    expect(bands[0][0].extendData.isCurrent).toBe(false)
    // 마지막 세그먼트: 현재 강조 + 번호+글리프 라벨.
    expect(bands[1][0].extendData.isCurrent).toBe(true)
    expect(bands[1][0].extendData.label).toBe('4▼')
  })

  it('stageSegments 없으면 stage band 미생성 + 범례 없음', () => {
    const { container } = render(
      <KLineChartPanel candles={CANDLES} indicatorConfig={INDICATOR_CONFIG} valuation={null} />,
    )
    const bands = chart.createOverlay.mock.calls.filter((c) => c[0]?.name === 'gcStageBand')
    expect(bands).toHaveLength(0)
    expect(container.querySelector('.kline__ribbon-legend')).toBeNull()
  })

  it('세그먼트 있으면 범례 렌더', () => {
    const { container } = render(
      <KLineChartPanel
        candles={CANDLES}
        indicatorConfig={INDICATOR_CONFIG}
        valuation={null}
        stageSegments={SEGMENTS}
        currentStage={4}
      />,
    )
    expect(container.querySelector('.kline__ribbon-legend')).toBeTruthy()
  })
})
