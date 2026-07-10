import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import App from './App.jsx'

// App 레이아웃 계약(IMP-17 jsdom) — Phase A 2컬럼 UX의 경계면만 검증한다:
//   (1) 랜딩 = 관심종목이 우측 패널에 렌더(모달 아님, 인라인).
//   (2) 좌측 ChatPanel 의 onShowPanel → 우측 패널 spec 리프팅(채팅 구동 경로).
//   (3) 우측 퀵버튼 → 대화 없이 패널 전환(직접 탐색 경로).
//   (4) 목표가 60s 폴링이 App 레벨로 이관돼 패널 내용과 무관하게 알림이 뜬다(IMP-11 보존).
// 자식(RightPanel·ChatPanel)은 테스트 더블로 대체해 App 의 상태 리프팅·배선만 좁게 확인한다.

// ChatPanel: onShowPanel 을 노출하는 버튼만 가진 더블(스트리밍 상태기계는 자체 테스트 영역).
vi.mock('./components/ChatPanel.jsx', () => ({
  default: ({ onShowPanel }) => (
    <div data-testid="chat-panel">
      <button
        type="button"
        onClick={() => onShowPanel({ kind: 'macro_dashboard', args: {}, valid: true })}
      >
        chat-open-macro
      </button>
    </div>
  ),
}))

// RightPanel: 받은 spec.kind 와 퀵버튼(onSelect)만 노출하는 더블(본문 라우팅은 RightPanel 자체 테스트).
vi.mock('./components/RightPanel.jsx', () => ({
  default: ({ spec, onSelect }) => (
    <div data-testid="right-panel">
      <span data-testid="right-kind">{spec ? spec.kind : 'empty'}</span>
      <button
        type="button"
        onClick={() => onSelect({ kind: 'balance', args: {}, valid: true })}
      >
        quick-balance
      </button>
    </div>
  ),
}))

// 목표가 폴링(App 레벨 이관) — fetchWatchlist mock 으로 전이 감지 경로만 태운다.
vi.mock('./api.js', () => ({ fetchWatchlist: vi.fn() }))
import { fetchWatchlist } from './api.js'

const wlView = (status) => ({
  items: [
    {
      ticker: '005930',
      stock_name: '삼성전자',
      target_status: status,
      target_price: 80000,
      current_price: 79000,
    },
  ],
  regime: null,
  partial_failure: [],
})

beforeEach(() => {
  vi.useFakeTimers()
  fetchWatchlist.mockReset()
  fetchWatchlist.mockResolvedValue(wlView('far'))
})
afterEach(() => {
  vi.runOnlyPendingTimers()
  vi.useRealTimers()
})

describe('App 2컬럼 레이아웃(모달 폐기 · 우측 동적 패널)', () => {
  it('랜딩 = 관심종목(watchlist)이 우측 패널에 렌더', () => {
    render(<App />)
    expect(screen.getByTestId('right-kind')).toHaveTextContent('watchlist')
    expect(screen.getByTestId('chat-panel')).toBeInTheDocument()
  })

  it('ChatPanel onShowPanel → 우측 패널 spec 전환(채팅 구동)', () => {
    render(<App />)
    fireEvent.click(screen.getByText('chat-open-macro'))
    expect(screen.getByTestId('right-kind')).toHaveTextContent('macro_dashboard')
  })

  it('RightPanel 퀵버튼 onSelect → 우측 패널 spec 전환(직접 탐색)', () => {
    render(<App />)
    fireEvent.click(screen.getByText('quick-balance'))
    expect(screen.getByTestId('right-kind')).toHaveTextContent('balance')
  })
})

describe('목표가 능동 알림 — App 레벨 폴링(패널 무관, IMP-11 보존)', () => {
  it('far→reached 전이 시 앱레벨 배너 노출', async () => {
    // 1차 far(기준 스냅샷) → 2차 reached(전이) 로 바꾼다.
    fetchWatchlist.mockResolvedValueOnce(wlView('far')).mockResolvedValueOnce(wlView('reached'))
    render(<App />)
    // 마운트 첫 조회(far) 소진 — 첫 관측은 알림 억제(스냅샷 확보). fake timer 하 microtask flush.
    await act(async () => {})
    expect(fetchWatchlist).toHaveBeenCalledTimes(1)
    expect(screen.queryByText(/목표가/)).not.toBeInTheDocument() // 첫 관측은 무발화
    // 60s 경과 → 2차 조회(reached) → 전이 감지 → 배너.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })
    expect(fetchWatchlist).toHaveBeenCalledTimes(2)
    expect(screen.getByText(/목표가/)).toBeInTheDocument()
  })

  it('first-observation reached → 무발화(마운트 무더기 알림 방지)', async () => {
    fetchWatchlist.mockResolvedValue(wlView('reached'))
    render(<App />)
    await act(async () => {})
    // 첫 관측은 prevMap 없음 → detectTargetAlerts 0(스팸 방지). 배너 없음.
    expect(screen.queryByText(/목표가/)).not.toBeInTheDocument()
  })
})
