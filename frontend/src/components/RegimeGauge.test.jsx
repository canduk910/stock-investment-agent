import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import RegimeGauge from './RegimeGauge.jsx'

// 통합 사분면 계약 — 정적 .quadrant 제거·라이브 판정을 RegimeTrajectory 에 주입·주변 카드 유지.
vi.mock('../api.js', () => ({ fetchMacroRegime: vi.fn() }))
import { fetchMacroRegime } from '../api.js'

vi.mock('./RegimeTrajectory.jsx', () => ({
  default: ({ live }) => (
    <div data-testid="rtraj">
      rtraj:{live ? `${live.regime}/${live.cs}/${live.ss}/${live.cash}/${live.cycleSign}` : 'nolive'}
    </div>
  ),
}))
vi.mock('./MacroIndicatorCards.jsx', () => ({ default: () => <div data-testid="cards">cards</div> }))

const REGIME = {
  regime: '확장',
  recommended_cash_ratio: 60,
  confidence: 'high',
  axes: { cycle: { score: 2, sign: '양호' }, sentiment: { score: 0, sign: '중립' } },
  vix_panic: false,
  missing_indicators: [],
  indicator_breakdown: [],
}

beforeEach(() => {
  fetchMacroRegime.mockReset().mockResolvedValue(REGIME)
})

describe('RegimeGauge — 통합 사분면', () => {
  it('정적 .quadrant 미렌더 + RegimeTrajectory 에 라이브 판정(regime/cs/ss/cash/sign) 주입', async () => {
    const { container } = render(<RegimeGauge />)
    await waitFor(() => expect(screen.getByTestId('rtraj')).toBeInTheDocument())
    // 정적 사분면·마커 제거됨(중복 사분면 없음).
    expect(container.querySelector('.quadrant')).toBeNull()
    expect(container.querySelector('.quadrant__marker')).toBeNull()
    // 라이브 판정이 통합 사분면에 전달됨.
    expect(screen.getByTestId('rtraj')).toHaveTextContent('rtraj:확장/2/0/60/양호')
  })

  it('현금비중·신뢰도·지표카드는 사분면 밖 카드로 유지', async () => {
    const { container } = render(<RegimeGauge />)
    await waitFor(() => expect(screen.getByTestId('cards')).toBeInTheDocument())
    expect(screen.getByText(/권장 현금비중/)).toBeInTheDocument()
    expect(container.querySelector('.cash-ratio__value')?.textContent).toContain('60')
    expect(screen.getByText(/신뢰도/)).toBeInTheDocument()
  })

  it('조회 실패 → 재시도 버튼(크래시 없이 reload) — onClick={reload} 회귀 잠금', async () => {
    fetchMacroRegime
      .mockReset()
      .mockRejectedValueOnce(new Error('FRED down'))
      .mockResolvedValue(REGIME)
    render(<RegimeGauge />)
    await waitFor(() => expect(screen.getByText(/국면 조회 실패/)).toBeInTheDocument())
    // 재시도 버튼이 렌더되고(에러 분기가 ReferenceError 로 크래시하지 않음) 클릭 시 재조회.
    fireEvent.click(screen.getByRole('button', { name: /재시도/ }))
    await waitFor(() => expect(screen.getByTestId('rtraj')).toBeInTheDocument())
  })
})
