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
// 톱바 상태 칩(리브랜딩) — App 이 fetchMacroRegime 를 자체 조회(환각 차단)해 국면·현금비중·VIX 칩을 그린다.
// setViewContext — App 이 우측 패널 변경 시 현재 화면을 챗 세션 핀 컨텍스트로 고정(P1).
vi.mock('./api.js', () => ({
  fetchWatchlist: vi.fn(),
  fetchMacroRegime: vi.fn(),
  setViewContext: vi.fn(),
  setReportContext: vi.fn(),
  fetchConversations: vi.fn(),
  createConversation: vi.fn(),
  renameConversation: vi.fn(),
  deleteConversation: vi.fn(),
  recordVisit: vi.fn(),
  fetchSiteStats: vi.fn(),
}))
import {
  fetchWatchlist,
  fetchMacroRegime,
  setViewContext,
  fetchConversations,
  createConversation,
  recordVisit,
  fetchSiteStats,
} from './api.js'

// 인증 게이트 — App 이 마운트 시 fetchMe 로 로그인 상태를 확인한다. 기본은 로그인됨(메인 앱 렌더).
vi.mock('./auth.js', () => ({
  fetchMe: vi.fn(),
  logout: vi.fn(),
  login: vi.fn(),
  signup: vi.fn(),
}))
import { fetchMe, logout } from './auth.js'

const regimeView = (over = {}) => ({
  regime: '확장',
  recommended_cash_ratio: 20,
  vix_panic: false,
  partial_failure: [],
  ...over,
})

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
  fetchMacroRegime.mockReset()
  fetchMacroRegime.mockResolvedValue(regimeView())
  setViewContext.mockReset()
  setViewContext.mockResolvedValue({ ok: true, set: true })
  fetchMe.mockReset()
  fetchMe.mockResolvedValue({ id: 1, email: 'a@b.com' }) // 기본: 로그인됨
  logout.mockReset()
  fetchConversations.mockReset()
  fetchConversations.mockResolvedValue({ conversations: [{ id: 1, title: '대화' }] })
  createConversation.mockReset()
  createConversation.mockResolvedValue({ id: 2, title: '새 대화' })
  recordVisit.mockReset()
  recordVisit.mockResolvedValue({ total_visits: 1234, today_visits: 12 })
  fetchSiteStats.mockReset()
  fetchSiteStats.mockResolvedValue({ member_count: 42, total_visits: 1234, today_visits: 12 })
})
afterEach(() => {
  vi.runOnlyPendingTimers()
  vi.useRealTimers()
})

// 로그인 상태로 App 렌더 — fetchMe 해결(authChecked+user)까지 기다린 뒤 메인 앱이 나온다.
async function renderLoggedIn() {
  render(<App />)
  await act(async () => {})
}

describe('App 2컬럼 레이아웃(모달 폐기 · 우측 동적 패널)', () => {
  it('랜딩 = 관심종목(watchlist)이 우측 패널에 렌더', async () => {
    await renderLoggedIn()
    expect(screen.getByTestId('right-kind')).toHaveTextContent('watchlist')
    expect(screen.getByTestId('chat-panel')).toBeInTheDocument()
  })

  it('ChatPanel onShowPanel → 우측 패널 spec 전환(채팅 구동)', async () => {
    await renderLoggedIn()
    fireEvent.click(screen.getByText('chat-open-macro'))
    expect(screen.getByTestId('right-kind')).toHaveTextContent('macro_dashboard')
  })

  it('RightPanel 퀵버튼 onSelect → 우측 패널 spec 전환(직접 탐색)', async () => {
    await renderLoggedIn()
    fireEvent.click(screen.getByText('quick-balance'))
    expect(screen.getByTestId('right-kind')).toHaveTextContent('balance')
  })
})

describe('인증 게이트', () => {
  it('비로그인(fetchMe→null) → LoginScreen 렌더, 메인 앱 미노출', async () => {
    fetchMe.mockResolvedValue(null)
    render(<App />)
    await act(async () => {})
    expect(screen.getByText('디케이 투자에이전트')).toBeInTheDocument() // 로그인 화면 브랜드
    expect(screen.queryByTestId('right-panel')).not.toBeInTheDocument() // 메인 앱 미노출
    expect(screen.getAllByText(/회원가입/).length).toBeGreaterThan(0)
  })

  it('로그인 상태 → 톱바에 이메일 + 로그아웃, 로그아웃 시 LoginScreen 복귀', async () => {
    await renderLoggedIn()
    expect(screen.getByText('a@b.com')).toBeInTheDocument()
    fireEvent.click(screen.getByText('로그아웃'))
    expect(logout).toHaveBeenCalled()
    // user null → LoginScreen(메인 앱 미노출).
    expect(screen.queryByTestId('right-panel')).not.toBeInTheDocument()
  })
})

describe('현재 화면 → 챗 세션 핀 컨텍스트(P1, 패널 변경 시)', () => {
  it('패널을 잔고로 전환 → 디바운스 후 setViewContext(balance) 발화', async () => {
    render(<App />)
    await act(async () => {}) // 랜딩(watchlist) 마운트 발화 소진
    setViewContext.mockClear()
    fireEvent.click(screen.getByText('quick-balance'))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400) // 디바운스 경과
    })
    expect(setViewContext).toHaveBeenCalledTimes(1)
    expect(setViewContext.mock.calls[0][1]).toBe('balance') // 두번째 인자 = kind
  })

  it('비데이터 화면(macro_dashboard) 전환 → kind=null 로 이전 핀 해제', async () => {
    render(<App />)
    await act(async () => {})
    setViewContext.mockClear()
    fireEvent.click(screen.getByText('chat-open-macro')) // onShowPanel(macro_dashboard)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })
    expect(setViewContext).toHaveBeenCalledTimes(1)
    expect(setViewContext.mock.calls[0][1]).toBe(null) // 비데이터 → 해제
  })

  it('랜딩(watchlist) 마운트 시 1회 발화(현재 보는 화면 = 관심종목)', async () => {
    render(<App />)
    await act(async () => {}) // fetchMe + fetchConversations 해결 → conversationId 설정
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400) // 디바운스 경과 → 랜딩 핀 발화
    })
    expect(setViewContext).toHaveBeenCalled()
    expect(setViewContext.mock.calls[0][1]).toBe('watchlist')
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

describe('톱바 리브랜딩 — 디케이 브랜드 + 상태 칩(자체 조회)', () => {
  it('워드마크 "디케이 투자에이전트" 렌더', async () => {
    render(<App />)
    await act(async () => {})
    expect(screen.getByText('디케이 투자에이전트')).toBeInTheDocument()
  })

  it('연세대학교 소속 헤드라인(대학명 + 과목명) 렌더', async () => {
    render(<App />)
    await act(async () => {})
    expect(screen.getByText('정보대학원 AI핀테크')).toBeInTheDocument()
    expect(screen.getByText('[AI핀테크Agent분석과 설계]')).toBeInTheDocument()
    // 연세 엠블럼(공식 CI 이미지) — alt 로 접근성 확인.
    expect(screen.getByAltText('연세대학교 로고')).toBeInTheDocument()
  })

  it('regime 조회 성공 시 국면·현금비중 상태 칩 렌더', async () => {
    render(<App />)
    await act(async () => {})
    // 국면명(확장)·현금비중(20%)이 톱바 칩에 반영된다.
    expect(screen.getByText(/확장/)).toBeInTheDocument()
    expect(screen.getByText(/20\s*%/)).toBeInTheDocument()
  })

  it('헤드라인에 가입자수·방문수(누적·오늘) 표시', async () => {
    render(<App />)
    await act(async () => {})
    await act(async () => {})
    expect(screen.getByText('가입자')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument() // member_count
    expect(screen.getByText('방문')).toBeInTheDocument()
    expect(screen.getByText(/오늘 12/)).toBeInTheDocument() // today_visits
  })

  it('vix_panic:true → VIX 패닉 위험 칩 노출', async () => {
    fetchMacroRegime.mockResolvedValue(regimeView({ vix_panic: true }))
    render(<App />)
    await act(async () => {})
    expect(screen.getByText(/VIX 패닉/)).toBeInTheDocument()
  })

  it('vix_panic:false → VIX 패닉 칩 미노출', async () => {
    render(<App />)
    await act(async () => {})
    expect(screen.queryByText(/VIX 패닉/)).not.toBeInTheDocument()
  })

  it('regime 조회 실패해도 앱은 렌더(칩만 생략) — 전체 에러 화면 금지', async () => {
    fetchMacroRegime.mockRejectedValue(new Error('boom'))
    render(<App />)
    await act(async () => {})
    // 톱바 워드마크는 여전히 뜨고, 상태 칩만 조용히 생략.
    expect(screen.getByText('디케이 투자에이전트')).toBeInTheDocument()
    expect(screen.queryByText(/VIX 패닉/)).not.toBeInTheDocument()
  })
})
