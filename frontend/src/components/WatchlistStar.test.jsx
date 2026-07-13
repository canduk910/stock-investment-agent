import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import WatchlistStar from './WatchlistStar.jsx'

// 종목 리포트 헤더의 관심종목 별 토글(항목7) — 경계(api.js)만 mock, 토글/멤버십/409 로직은 실제 통과.
//   관심종목=조회·저장(매매 아님)·사용자 명시적 클릭만. 409(상한 30) graceful.

vi.mock('../api.js', () => ({
  fetchWatchlistMembership: vi.fn(),
  addWatchlist: vi.fn(),
  removeWatchlist: vi.fn(),
}))
import { fetchWatchlistMembership, addWatchlist, removeWatchlist } from '../api.js'

beforeEach(() => {
  vi.clearAllMocks()
  fetchWatchlistMembership.mockResolvedValue({ member: false })
})

describe('WatchlistStar — 관심종목 별 토글', () => {
  it('멤버십 true → ★ 등록완료 식별(is-on·aria-pressed=true)', async () => {
    fetchWatchlistMembership.mockResolvedValue({ ticker: '005930', member: true })
    render(<WatchlistStar ticker="005930" stockName="삼성전자" />)
    await waitFor(() =>
      expect(screen.getByRole('button', { pressed: true })).toBeInTheDocument(),
    )
    expect(screen.getByRole('button').className).toContain('is-on')
    expect(screen.getByText('★')).toBeInTheDocument()
  })

  it('멤버십 false → ☆ 미등록(aria-pressed=false)', async () => {
    fetchWatchlistMembership.mockResolvedValue({ member: false })
    render(<WatchlistStar ticker="005930" stockName="삼성전자" />)
    await waitFor(() => expect(fetchWatchlistMembership).toHaveBeenCalledWith('005930'))
    expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByText('☆')).toBeInTheDocument()
  })

  it('☆ 클릭 → addWatchlist({ticker,stockName}) → ★ + 담김 안내', async () => {
    fetchWatchlistMembership.mockResolvedValue({ member: false })
    addWatchlist.mockResolvedValue({ ok: true, item: {} })
    render(<WatchlistStar ticker="005930" stockName="삼성전자" />)
    await waitFor(() => expect(fetchWatchlistMembership).toHaveBeenCalled())
    fireEvent.click(screen.getByRole('button'))
    await waitFor(() =>
      expect(addWatchlist).toHaveBeenCalledWith({ ticker: '005930', stockName: '삼성전자' }),
    )
    await waitFor(() => expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'true'))
    expect(screen.getByText(/담았습니다/)).toBeInTheDocument()
  })

  it('★ 클릭 → removeWatchlist(ticker) → ☆ + 제거 안내', async () => {
    fetchWatchlistMembership.mockResolvedValue({ member: true })
    removeWatchlist.mockResolvedValue({ ok: true })
    render(<WatchlistStar ticker="005930" stockName="삼성전자" />)
    await waitFor(() => expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'true'))
    fireEvent.click(screen.getByRole('button'))
    await waitFor(() => expect(removeWatchlist).toHaveBeenCalledWith('005930'))
    await waitFor(() => expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'false'))
    expect(screen.getByText(/제거/)).toBeInTheDocument()
  })

  it('409 상한 → 담기 실패 안내(별은 ☆ 유지, 무한 스피너 없음)', async () => {
    fetchWatchlistMembership.mockResolvedValue({ member: false })
    const err = new Error('API 409')
    err.status = 409
    addWatchlist.mockRejectedValue(err)
    render(<WatchlistStar ticker="005930" stockName="삼성전자" />)
    await waitFor(() => expect(fetchWatchlistMembership).toHaveBeenCalled())
    fireEvent.click(screen.getByRole('button'))
    await waitFor(() => expect(screen.getByText(/가득 찼습니다/)).toBeInTheDocument())
    expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'false') // 여전히 미등록
    expect(screen.getByRole('button')).not.toBeDisabled() // busy 해제(무한 스피너 아님)
  })

  it('불량 ticker → 렌더 안 함(별 없음·멤버십 조회 안 함)', () => {
    const { container } = render(<WatchlistStar ticker="삼성" stockName="삼성전자" />)
    expect(container.querySelector('button')).toBeNull()
    expect(fetchWatchlistMembership).not.toHaveBeenCalled()
  })
})
