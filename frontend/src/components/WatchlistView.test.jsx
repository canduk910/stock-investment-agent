import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import WatchlistView from './WatchlistView.jsx'

// 컴포넌트 렌더 스모크(IMP-17) — API 경계만 mock, 배지·배너 로직은 실제 통과.
vi.mock('../api.js', () => ({
  fetchWatchlist: vi.fn(),
  removeWatchlist: vi.fn(),
  updateWatchlistTarget: vi.fn(),
}))
import { fetchWatchlist, updateWatchlistTarget } from '../api.js'

const _item = (o) => ({
  ticker: o.ticker,
  stock_name: o.name,
  current_price: o.price ?? null,
  change_rate: o.cr ?? null,
  per: o.per ?? null,
  pbr: o.pbr ?? null,
  target_price: o.buy ?? null,
  distance_to_target: o.buyDist ?? null,
  target_status: o.buyStatus ?? 'none',
  sell_target_price: o.sell ?? null,
  sell_distance_to_target: o.sellDist ?? null,
  sell_target_status: o.sellStatus ?? 'none',
  added_at: '2026-01-01T00:00:00Z',
  reason: null,
})

beforeEach(() => {
  fetchWatchlist.mockReset()
  updateWatchlistTarget.mockReset()
})

describe('WatchlistView 렌더 스모크(IMP-17)', () => {
  it('부분실패 배너 + 국면명 배너(현금비중만) + 시세실패 표시', async () => {
    // 항목3: 종목 진입신호(entry_signal) 폐기 — 배지 없음. 국면 배너는 국면명만.
    fetchWatchlist.mockResolvedValue({
      items: [
        _item({
          ticker: '005930', name: '삼성전자', price: 80000, cr: 1.2, per: 12, pbr: 1.1,
        }),
        _item({ ticker: '000660', name: 'SK하이닉스' }), // 시세 실패
      ],
      regime: { regime: '수축' }, // 국면명만(single_cap/entry_blocked 없음)
      partial_failure: ['000660'],
      sort_by: 'registered',
    })
    render(<WatchlistView />)
    await waitFor(() => expect(screen.getByText('삼성전자')).toBeInTheDocument())
    expect(screen.getByText(/일부 종목 시세 일시 조회 불가/)).toBeInTheDocument()
    expect(screen.getByText('수축')).toBeInTheDocument() // 국면명 배너
    expect(screen.queryByText(/진입 검토 가능|진입 판정 불가/)).toBeNull() // 진입 배지 없음
    expect(screen.getByText('조회 불가')).toBeInTheDocument() // 시세 실패 셀
  })

  it('빈 목록 안내', async () => {
    fetchWatchlist.mockResolvedValue({ items: [], regime: null, partial_failure: [], sort_by: 'registered' })
    render(<WatchlistView />)
    await waitFor(() => expect(screen.getByText(/관심종목이 없습니다/)).toBeInTheDocument())
  })

  it('매수·매도 목표가 2행 렌더(라벨·값·side 배지)', async () => {
    fetchWatchlist.mockResolvedValue({
      items: [_item({
        ticker: '005930', name: '삼성전자', price: 88000, cr: 1.0,
        buy: 80000, buyDist: 10, buyStatus: 'far',
        sell: 100000, sellDist: 0, sellStatus: 'reached',
      })],
      regime: null, partial_failure: [], sort_by: 'registered',
    })
    render(<WatchlistView />)
    await waitFor(() => expect(screen.getByText('삼성전자')).toBeInTheDocument())
    // 매수/매도 라벨 2행 + 각 목표가 값.
    expect(screen.getByText('매수')).toBeInTheDocument()
    expect(screen.getByText('매도')).toBeInTheDocument()
    expect(screen.getByText('80,000원')).toBeInTheDocument()
    expect(screen.getByText('100,000원')).toBeInTheDocument()
    // 매도 도달 배지(side 라벨로 구분).
    expect(screen.getByText('매도 목표가 도달')).toBeInTheDocument()
  })

  it('매도 목표가 편집 → updateWatchlistTarget(ticker, {sell_target_price}) 호출(매수 불변)', async () => {
    fetchWatchlist.mockResolvedValue({
      items: [_item({ ticker: '005930', name: '삼성전자', price: 88000, cr: 1.0 })],
      regime: null, partial_failure: [], sort_by: 'registered',
    })
    updateWatchlistTarget.mockResolvedValue({ ok: true, item: {} })
    render(<WatchlistView />)
    await waitFor(() => expect(screen.getByText('삼성전자')).toBeInTheDocument())
    // 둘 다 미설정 → '설정' 버튼 2개(매수·매도 순). 매도(두 번째) 편집.
    fireEvent.click(screen.getAllByText('설정')[1])
    const input = screen.getByLabelText('매도 목표가 입력(원)')
    fireEvent.change(input, { target: { value: '120000' } })
    fireEvent.submit(input.closest('form'))
    await waitFor(() =>
      expect(updateWatchlistTarget).toHaveBeenCalledWith('005930', { sell_target_price: 120000 }),
    )
  })
})
