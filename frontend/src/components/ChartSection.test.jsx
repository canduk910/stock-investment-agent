import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import ChartSection from './ChartSection.jsx'

// 경계(api.js·KLineChartPanel)만 mock — 선택기 렌더·조회 인자·차트 스왑·fallback 유지 검증.
vi.mock('../api.js', () => ({ fetchStockChart: vi.fn() }))
import { fetchStockChart } from '../api.js'

vi.mock('./KLineChartPanel.jsx', () => ({
  default: ({ candles, stageSegments, currentStage }) => (
    <div data-testid="kline">
      candles:{candles?.length ?? 'null'}|segs:{stageSegments?.length ?? 'null'}|stage:{String(currentStage)}
    </div>
  ),
}))

const FALLBACK_CANDLES = [{ date: '20260101', close: 1 }, { date: '20260102', close: 2 }]
const FALLBACK_SEGS = [{ stage: 4, start_date: '20260101', end_date: '20260102' }]
const CFG = { grand_cycle: { periods: { short: 5, medium: 20, long: 40 } } }

function renderCS() {
  return render(
    <ChartSection
      ticker="005930"
      fallbackCandles={FALLBACK_CANDLES}
      fallbackSegments={FALLBACK_SEGS}
      fallbackStage={4}
      indicatorConfig={CFG}
      valuation={null}
    />,
  )
}

beforeEach(() => {
  fetchStockChart.mockReset().mockResolvedValue({
    ticker: '005930', period: 'D', range: '1y',
    candles: [{ date: '20250101', close: 1 }, { date: '20250102', close: 2 }, { date: '20250103', close: 3 }],
    stage_segments: [{ stage: 1, start_date: '20250101', end_date: '20250103' }],
    current_stage: 1, partial_failure: [],
  })
})

describe('ChartSection', () => {
  it('주기·기간 선택기 렌더 + 마운트 시 기본(D/1y) 조회', async () => {
    renderCS()
    expect(screen.getByRole('button', { name: '일봉' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '주봉' })).toBeInTheDocument()
    for (const l of ['3개월', '1년', '3년', '10년']) {
      expect(screen.getByRole('button', { name: l })).toBeInTheDocument()
    }
    await waitFor(() => expect(fetchStockChart).toHaveBeenCalledWith('005930', 'D', '1y'))
  })

  it('조회 성공 후 그 데이터로 스왑(캔들·세그먼트·현재단계)', async () => {
    renderCS()
    await waitFor(() =>
      expect(screen.getByTestId('kline')).toHaveTextContent('candles:3|segs:1|stage:1'),
    )
  })

  it('주봉·기간 클릭 → 해당 인자로 재조회', async () => {
    renderCS()
    await waitFor(() => expect(fetchStockChart).toHaveBeenCalledWith('005930', 'D', '1y'))
    fireEvent.click(screen.getByRole('button', { name: '주봉' }))
    await waitFor(() => expect(fetchStockChart).toHaveBeenCalledWith('005930', 'W', '1y'))
    fireEvent.click(screen.getByRole('button', { name: '3년' }))
    await waitFor(() => expect(fetchStockChart).toHaveBeenCalledWith('005930', 'W', '3y'))
  })

  it('기본 active 표시(aria-pressed) — 일봉·1년', () => {
    renderCS()
    expect(screen.getByRole('button', { name: '일봉' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '1년' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '주봉' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('조회 실패 시 fallback 차트 유지(빈 화면 아님)', async () => {
    fetchStockChart.mockRejectedValue(new Error('API 500'))
    renderCS()
    await waitFor(() =>
      expect(screen.getByTestId('kline')).toHaveTextContent('candles:2|segs:1|stage:4'),
    )
  })
})
