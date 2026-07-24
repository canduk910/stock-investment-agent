import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import ScreenerPanel from './ScreenerPanel.jsx'

// 경계(api.js)만 mock. 카드 렌더·종목명·단계 배지·단계 필터·시장 선택기·클릭 네비·graceful 검증.

vi.mock('../api.js', () => ({ fetchScreener: vi.fn() }))
import { fetchScreener } from '../api.js'

const CATALOG = {
  periods: { short: 5, medium: 20, long: 40 },
  stages: [
    { stage: 1, name: '안정 상승기', arrangement: '단>중>장', phase: '상승' },
    { stage: 4, name: '안정 하락기', arrangement: '장>중>단', phase: '하락' },
    { stage: 6, name: '상승 진입기', arrangement: '단>장>중', phase: '상승' },
  ],
}

function resp(overrides = {}) {
  return {
    candidates: [
      { ticker: '005930', name: '삼성전자', price: 78000, change_rate: -7.5, market_cap: 14586465, stage: 4, stage_name: '안정 하락기', band_width_pct: -16.9, band_direction: '확대', bars_in_stage: 10 },
      { ticker: '207940', name: '삼성바이오로직스', price: 1000000, change_rate: 10.08, market_cap: 700000, stage: 1, stage_name: '안정 상승기', band_width_pct: 2.6, band_direction: '축소', bars_in_stage: 5 },
      { ticker: '000660', name: 'SK하이닉스', price: 180000, change_rate: -8.3, market_cap: 12536435, stage: 6, stage_name: '상승 진입기', band_width_pct: 1.2, band_direction: '확대', bars_in_stage: 2 },
      { ticker: '999999', name: '봉부족주', price: 1000, change_rate: 0, market_cap: 1000, stage: null, stage_name: null, band_width_pct: null, band_direction: null, bars_in_stage: 0 },
    ],
    catalog: CATALOG,
    market: 'all', market_iscd: '0000', size: 30, partial_failure: [],
    ...overrides,
  }
}

beforeEach(() => {
  fetchScreener.mockReset().mockResolvedValue(resp())
})

describe('ScreenerPanel', () => {
  it('기본(상승국면) 필터 — 상승 단계(1·6) 종목만 종목명+단계 배지로 렌더', async () => {
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText('삼성바이오로직스')).toBeInTheDocument())
    // 상승국면(1·6): 삼성바이오(1)·SK하이닉스(6) 표시, 하락(4) 삼성전자·판정보류(null)는 숨김
    expect(screen.getByText('SK하이닉스')).toBeInTheDocument()
    expect(screen.queryByText('삼성전자')).not.toBeInTheDocument()
    expect(screen.queryByText('봉부족주')).not.toBeInTheDocument()
    // 단계 배지(라벨) — 종목명 미표시 문제 해결의 핵심(종목명 + 단계)
    expect(screen.getByText(/1단계 · 안정 상승기/)).toBeInTheDocument()
    expect(screen.getByText(/6단계 · 상승 진입기/)).toBeInTheDocument()
  })

  it("단계 필터 '전체' → 하락 단계·판정보류 종목까지 표시", async () => {
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText('삼성바이오로직스')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: '전체 단계' }))
    await waitFor(() => expect(screen.getByText('삼성전자')).toBeInTheDocument())
    expect(screen.getByText(/4단계 · 안정 하락기/)).toBeInTheDocument()
    expect(screen.getByText('봉부족주')).toBeInTheDocument()
    expect(screen.getByText(/판정 보류/)).toBeInTheDocument()
  })

  it('시장 선택기 → 해당 market 으로 재조회', async () => {
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText('삼성바이오로직스')).toBeInTheDocument())
    expect(fetchScreener).toHaveBeenCalledWith('all', 30)
    fireEvent.click(screen.getByRole('button', { name: '코스피200' }))
    await waitFor(() => expect(fetchScreener).toHaveBeenCalledWith('kospi200', 30))
  })

  it('후보 카드 클릭 → onOpenStock(ticker, name)', async () => {
    const onOpenStock = vi.fn()
    render(<ScreenerPanel onOpenStock={onOpenStock} />)
    await waitFor(() => expect(screen.getByText('SK하이닉스')).toBeInTheDocument())
    fireEvent.click(screen.getByText('SK하이닉스'))
    expect(onOpenStock).toHaveBeenCalledWith('000660', 'SK하이닉스')
  })

  it('로딩 상태 표시', async () => {
    let resolve
    fetchScreener.mockReturnValue(new Promise((r) => { resolve = r }))
    render(<ScreenerPanel />)
    expect(screen.getByText(/스캔하는 중/)).toBeInTheDocument()
    resolve(resp())
    await waitFor(() => expect(screen.getByText('삼성바이오로직스')).toBeInTheDocument())
  })

  it('조회 실패 → 안내 + 다시 시도(무한 스피너 금지)', async () => {
    fetchScreener.mockRejectedValue(new Error('boom'))
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText(/후보 조회에 실패/)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: '다시 시도' })).toBeInTheDocument()
  })

  it('partial_failure → 안내 노트', async () => {
    fetchScreener.mockResolvedValue(resp({ partial_failure: ['999999'] }))
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText(/일부 종목은 일시 조회 실패/)).toBeInTheDocument())
  })

  it('면책 고지 상시 노출', async () => {
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText(/투자 책임은/)).toBeInTheDocument())
  })
})
