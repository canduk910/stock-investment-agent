import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import MacroIndicatorCards from './MacroIndicatorCards.jsx'

// 판정근거 4지표 카드(값+구간+축) + 카드 클릭 → 최근 5년 히스토리 오버레이. api 경계만 mock.
vi.mock('../api.js', () => ({ fetchMacroIndicatorHistory: vi.fn() }))
import { fetchMacroIndicatorHistory } from '../api.js'

const BREAKDOWN = [
  { key: 'yield_spread', label: '장단기 금리차', value: 0.35, unit: '%p', zone: '중립', axis: '경기', source: 'FRED', thresholds: { lo: 0, hi: 0.5 } },
  { key: 'hy_spread', label: 'HY 신용스프레드', value: 6.0, unit: '%', zone: '악화', axis: '경기', source: 'FRED', thresholds: { lo: 3, hi: 5 } },
  { key: 'vix', label: 'VIX 변동성', value: 30, unit: '', zone: '공포', axis: '심리', source: 'FRED/Yahoo', thresholds: { lo: 14, hi: 28 } },
  { key: 'fear_greed', label: '공포탐욕지수', value: null, unit: '/100', zone: null, axis: '심리', source: 'CNN', thresholds: { lo: 25, hi: 75 } },
]

beforeEach(() => fetchMacroIndicatorHistory.mockReset())

describe('MacroIndicatorCards', () => {
  it('판정 4지표 카드 — 값·구간·축 그룹(경기/심리) 렌더', () => {
    render(<MacroIndicatorCards breakdown={BREAKDOWN} />)
    // 라벨·값·구간.
    expect(screen.getByText('VIX 변동성')).toBeInTheDocument()
    expect(screen.getByText('30.00')).toBeInTheDocument()
    expect(screen.getByText('공포')).toBeInTheDocument()
    expect(screen.getByText('악화')).toBeInTheDocument()
    expect(screen.getByText('중립')).toBeInTheDocument()
    // 축 그룹.
    expect(screen.getByText('경기')).toBeInTheDocument()
    expect(screen.getByText('심리')).toBeInTheDocument()
    // 누락 지표(fear_greed value null) → 데이터 없음.
    expect(screen.getByText('데이터 없음')).toBeInTheDocument()
  })

  it('빈 breakdown → 렌더 안 함', () => {
    const { container } = render(<MacroIndicatorCards breakdown={[]} />)
    expect(container.querySelector('.macro-cards')).toBeFalsy()
  })

  it('카드 클릭 → 히스토리 오버레이 + fetchMacroIndicatorHistory(key) 호출 + 차트', async () => {
    fetchMacroIndicatorHistory.mockResolvedValue({
      key: 'vix', label: 'VIX 변동성', unit: '', source: 'FRED', thresholds: { lo: 14, hi: 28 },
      months: 12, available: true,
      points: [
        { date: '2025-10-01', value: 16 },
        { date: '2025-11-01', value: 22 },
        { date: '2025-12-01', value: 30 },
      ],
    })
    render(<MacroIndicatorCards breakdown={BREAKDOWN} />)
    fireEvent.click(screen.getByRole('button', { name: 'VIX 변동성 최근 5년 히스토리 보기' }))
    await waitFor(() => expect(fetchMacroIndicatorHistory).toHaveBeenCalledWith('vix', 60))
    // 오버레이(dialog) + 라인차트 렌더.
    const dialog = await screen.findByRole('dialog')
    await waitFor(() => expect(dialog.querySelector('path.macro-chart__line')).toBeTruthy())
  })

  it('히스토리 미제공(available:false) → 오버레이에 안내(현재값만)', async () => {
    fetchMacroIndicatorHistory.mockResolvedValue({
      key: 'fear_greed', label: '공포탐욕지수', unit: '/100', source: 'CNN',
      thresholds: { lo: 25, hi: 75 }, months: 12, available: false, points: [],
      note: '이 지표는 히스토리를 제공하지 못했습니다(현재값만 참고하세요).',
    })
    render(<MacroIndicatorCards breakdown={BREAKDOWN} />)
    fireEvent.click(screen.getByRole('button', { name: '공포탐욕지수 최근 5년 히스토리 보기' }))
    await screen.findByRole('dialog')
    await waitFor(() => expect(screen.getByText(/현재값만 참고/)).toBeInTheDocument())
  })

  it('오버레이 Esc 닫힘', async () => {
    fetchMacroIndicatorHistory.mockResolvedValue({
      key: 'vix', label: 'VIX 변동성', unit: '', source: 'FRED', thresholds: { lo: 14, hi: 28 },
      months: 12, available: true,
      points: [{ date: '2025-11-01', value: 22 }, { date: '2025-12-01', value: 30 }],
    })
    render(<MacroIndicatorCards breakdown={BREAKDOWN} />)
    fireEvent.click(screen.getByRole('button', { name: 'VIX 변동성 최근 5년 히스토리 보기' }))
    await screen.findByRole('dialog')
    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })
})
