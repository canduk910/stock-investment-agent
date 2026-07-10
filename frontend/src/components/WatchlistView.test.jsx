import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import WatchlistView from './WatchlistView.jsx'

// 컴포넌트 렌더 스모크(IMP-17) — API 경계만 mock, 배지·배너 로직은 실제 통과.
vi.mock('../api.js', () => ({
  fetchWatchlist: vi.fn(),
  removeWatchlist: vi.fn(),
  updateWatchlistTarget: vi.fn(),
}))
import { fetchWatchlist } from '../api.js'

const _item = (o) => ({
  ticker: o.ticker,
  stock_name: o.name,
  current_price: o.price ?? null,
  change_rate: o.cr ?? null,
  per: o.per ?? null,
  pbr: o.pbr ?? null,
  target_price: null,
  distance_to_target: null,
  target_status: 'none',
  added_at: '2026-01-01T00:00:00Z',
  reason: null,
  entry_signal: o.sig ?? null,
})

beforeEach(() => fetchWatchlist.mockReset())

describe('WatchlistView 렌더 스모크(IMP-17)', () => {
  it('부분실패 배너 + entry_signal 배지(검토가능/판정불가) + 시세실패 표시', async () => {
    fetchWatchlist.mockResolvedValue({
      items: [
        _item({
          ticker: '005930', name: '삼성전자', price: 80000, cr: 1.2, per: 12, pbr: 1.1,
          sig: { entry_blocked: false, per_over: false, pbr_over: false, single_cap: 5, entry_allowed: true, note: 'x' },
        }),
        _item({ ticker: '000660', name: 'SK하이닉스', sig: null }), // 시세 실패 → entry_signal null
      ],
      regime: { regime: '수축', single_cap: 5, entry_blocked: false },
      partial_failure: ['000660'],
      sort_by: 'registered',
    })
    render(<WatchlistView />)
    await waitFor(() => expect(screen.getByText('삼성전자')).toBeInTheDocument())
    expect(screen.getByText(/일부 종목 시세 일시 조회 불가/)).toBeInTheDocument()
    expect(screen.getByText('진입 검토 가능')).toBeInTheDocument()
    expect(screen.getByText('진입 판정 불가')).toBeInTheDocument()
    expect(screen.getByText('조회 불가')).toBeInTheDocument() // 시세 실패 셀
  })

  it('빈 목록 안내', async () => {
    fetchWatchlist.mockResolvedValue({ items: [], regime: null, partial_failure: [], sort_by: 'registered' })
    render(<WatchlistView />)
    await waitFor(() => expect(screen.getByText(/관심종목이 없습니다/)).toBeInTheDocument())
  })
})
