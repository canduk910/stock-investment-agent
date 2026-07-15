import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import ManageWatchlistConfirm from './ManageWatchlistConfirm.jsx'

// 챗 자연어 편집 확인 카드 — set_target 매수/매도 분리(confirm-before-write). API 경계만 mock.
vi.mock('../api.js', () => ({
  addWatchlist: vi.fn(),
  removeWatchlist: vi.fn(),
  updateWatchlistTarget: vi.fn(),
}))
import { updateWatchlistTarget } from '../api.js'

beforeEach(() => updateWatchlistTarget.mockReset())

describe('ManageWatchlistConfirm — set_target 매수/매도 확인', () => {
  it('매도 목표가만 제안 → 문구에 매도만, 확인 시 {sell_target_price} 저장(자동 저장 아님)', async () => {
    updateWatchlistTarget.mockResolvedValue({ ok: true })
    render(
      <ManageWatchlistConfirm
        args={{ action: 'set_target', ticker: '005930', stock_name: '삼성전자', sell_target_price: 120000 }}
        valid
        onClose={() => {}}
      />,
    )
    expect(screen.getByText(/매도 목표가 120,000원/)).toBeInTheDocument()
    expect(screen.queryByText(/매수 목표가/)).toBeNull()
    // "AI 는 제안만" 문구 — 자동 실행 아님.
    expect(screen.getByText(/제안만/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('확인'))
    await waitFor(() =>
      expect(updateWatchlistTarget).toHaveBeenCalledWith('005930', { sell_target_price: 120000 }),
    )
  })

  it('매수+매도 둘 다 제안 → 문구에 둘 다, 확인 시 둘 다 저장', async () => {
    updateWatchlistTarget.mockResolvedValue({ ok: true })
    render(
      <ManageWatchlistConfirm
        args={{ action: 'set_target', ticker: '005930', target_price: 80000, sell_target_price: 120000 }}
        valid
        onClose={() => {}}
      />,
    )
    expect(screen.getByText(/매수 목표가 80,000원/)).toBeInTheDocument()
    expect(screen.getByText(/매도 목표가 120,000원/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('확인'))
    await waitFor(() =>
      expect(updateWatchlistTarget).toHaveBeenCalledWith('005930', {
        target_price: 80000,
        sell_target_price: 120000,
      }),
    )
  })
})
