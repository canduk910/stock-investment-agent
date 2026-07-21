import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import RightPanel from './RightPanel.jsx'

// RightPanel 계약 테스트(IMP-17 jsdom) — 우측 동적 패널의 두 경계면만 검증한다:
//   (1) 퀵버튼 툴바 → onSelect 로 올바른 kind spec 을 리프팅한다(대화 없이 직접 탐색).
//   (2) spec.kind → 대응 본문 컴포넌트를 인라인 렌더한다(모달 폐기, 재작성 0 재사용).
// 하위 팝업 컴포넌트는 각자 api 를 자체 조회하므로 여기선 mock 으로 "무엇이 렌더되는가"만 확인한다
// (실데이터·partial_failure 렌더는 각 컴포넌트 자체 스모크 테스트가 담당 — 여기서 중복 안 함).

vi.mock('./PopupStockReport.jsx', () => ({
  default: ({ ticker, stockName }) => (
    <div data-testid="stock-report">
      stock-report:{ticker}:{stockName ?? ''}
    </div>
  ),
}))
vi.mock('./PopupWatchlist.jsx', () => ({
  default: ({ args, onOpenStock }) => (
    <div data-testid="watchlist">
      watchlist:{args?.sort_by ?? ''}
      <button type="button" onClick={() => onOpenStock('005930', '삼성전자')}>wl-open</button>
    </div>
  ),
}))
vi.mock('./ManageWatchlistConfirm.jsx', () => ({
  default: ({ valid, onClose }) => (
    <div data-testid="manage">
      manage:{String(valid)}
      <button type="button" onClick={onClose}>manage-close</button>
    </div>
  ),
}))
vi.mock('./BalancePanel.jsx', () => ({
  default: ({ onOpenStock }) => (
    <div data-testid="balance">
      balance
      <button type="button" onClick={() => onOpenStock('000660', 'SK하이닉스')}>bal-open</button>
    </div>
  ),
}))
// macro_dashboard·settings 본문은 자체 api 조회형(시황 lifecycle 소유) — 라우팅만 보므로 스텁으로 대체.
vi.mock('./MacroDashboard.jsx', () => ({
  default: () => <div data-testid="macro-dashboard">macro-dashboard</div>,
}))
vi.mock('./KisSettingsPanel.jsx', () => ({
  default: () => <div data-testid="kis-settings">kis-settings</div>,
}))
vi.mock('./AdminPanel.jsx', () => ({
  default: ({ currentUserId }) => <div data-testid="admin">admin:{String(currentUserId)}</div>,
}))
// 종목검색 자동완성(항목6) — TickerSearch 가 searchStocks 를 부른다. 경계만 mock.
vi.mock('../api.js', () => ({ searchStocks: vi.fn() }))
import { searchStocks } from '../api.js'

const spec = (o) => ({ args: {}, valid: true, ...o })

beforeEach(() => {
  vi.clearAllMocks()
  searchStocks.mockResolvedValue([]) // 기본: 후보 없음(개별 테스트가 override)
})

describe('RightPanel 본문 라우팅(spec.kind → 인라인 컴포넌트)', () => {
  it('watchlist → PopupWatchlist(랜딩 기본)', () => {
    render(<RightPanel spec={spec({ kind: 'watchlist', args: { sort_by: 'change' } })} onSelect={() => {}} onClose={() => {}} />)
    expect(screen.getByTestId('watchlist')).toHaveTextContent('watchlist:change')
  })

  it('macro_dashboard → MacroDashboard(시황 컨테이너)', () => {
    render(<RightPanel spec={spec({ kind: 'macro_dashboard' })} onSelect={() => {}} onClose={() => {}} />)
    expect(screen.getByTestId('macro-dashboard')).toBeInTheDocument()
  })

  it('stock_report(valid) → PopupStockReport(ticker/stockName 전달)', () => {
    render(
      <RightPanel
        spec={spec({ kind: 'stock_report', args: { ticker: '005930', stock_name: '삼성전자' } })}
        onSelect={() => {}}
        onClose={() => {}}
      />,
    )
    expect(screen.getByTestId('stock-report')).toHaveTextContent('stock-report:005930:삼성전자')
  })

  it('stock_report(invalid) → 조회 없이 안내 문구(잘못된 백엔드 조회 방지)', () => {
    render(
      <RightPanel
        spec={{ kind: 'stock_report', args: { ticker: '삼성' }, valid: false }}
        onSelect={() => {}}
        onClose={() => {}}
      />,
    )
    expect(screen.queryByTestId('stock-report')).not.toBeInTheDocument()
    expect(screen.getByText(/종목 코드를 인식하지 못했어요/)).toBeInTheDocument()
  })

  it('balance → BalancePanel(자체조회 /api/balance)', () => {
    render(<RightPanel spec={spec({ kind: 'balance' })} onSelect={() => {}} onClose={() => {}} />)
    expect(screen.getByTestId('balance')).toBeInTheDocument()
  })

  it('manage_watchlist → ManageWatchlistConfirm(valid·onClose 전달)', () => {
    const onClose = vi.fn()
    render(
      <RightPanel
        spec={spec({ kind: 'manage_watchlist', args: { action: 'add', ticker: '005930' } })}
        onSelect={() => {}}
        onClose={onClose}
      />,
    )
    expect(screen.getByTestId('manage')).toHaveTextContent('manage:true')
    fireEvent.click(screen.getByText('manage-close'))
    expect(onClose).toHaveBeenCalled() // confirm 카드의 닫기 → 패널 비우기(onClose)로 연결
  })

  it('관심종목에서 onOpenStock → onSelect(stock_report spec) 리프팅(종목 클릭→상세)', () => {
    const onSelect = vi.fn()
    render(<RightPanel spec={spec({ kind: 'watchlist' })} onSelect={onSelect} onClose={() => {}} />)
    fireEvent.click(screen.getByText('wl-open'))
    expect(onSelect).toHaveBeenCalledWith({
      kind: 'stock_report',
      args: { ticker: '005930', stock_name: '삼성전자' },
      valid: true,
    })
  })

  it('잔고에서 onOpenStock → onSelect(stock_report spec) 리프팅(종목 클릭→상세)', () => {
    const onSelect = vi.fn()
    render(<RightPanel spec={spec({ kind: 'balance' })} onSelect={onSelect} onClose={() => {}} />)
    fireEvent.click(screen.getByText('bal-open'))
    expect(onSelect).toHaveBeenCalledWith({
      kind: 'stock_report',
      args: { ticker: '000660', stock_name: 'SK하이닉스' },
      valid: true,
    })
  })

  it('null spec → 빈 상태 안내(전체 에러 화면 아님)', () => {
    render(<RightPanel spec={null} onSelect={() => {}} onClose={() => {}} />)
    expect(screen.queryByTestId('watchlist')).not.toBeInTheDocument()
    // 빈 상태는 퀵버튼 툴바로 탐색을 유도한다(무한 스피너·에러 금지)
    expect(screen.getByRole('button', { name: '관심종목' })).toBeInTheDocument()
  })
})

describe('RightPanel 퀵버튼 툴바(대화 없이 직접 탐색 → onSelect 리프팅)', () => {
  it('국면 → {kind:macro_dashboard}', () => {
    const onSelect = vi.fn()
    render(<RightPanel spec={null} onSelect={onSelect} onClose={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: '시장 국면' }))
    expect(onSelect).toHaveBeenCalledWith({ kind: 'macro_dashboard', args: {}, valid: true })
  })

  it('관심종목 → {kind:watchlist}', () => {
    const onSelect = vi.fn()
    render(<RightPanel spec={null} onSelect={onSelect} onClose={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: '관심종목' }))
    expect(onSelect).toHaveBeenCalledWith({ kind: 'watchlist', args: {}, valid: true })
  })

  it('잔고 → {kind:balance} (UX4 배선 지점)', () => {
    const onSelect = vi.fn()
    render(<RightPanel spec={null} onSelect={onSelect} onClose={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: '내 잔고' }))
    expect(onSelect).toHaveBeenCalledWith({ kind: 'balance', args: {}, valid: true })
  })

  it('회원 관리 탭은 관리자만 노출된다(비관리자 미노출)', () => {
    const { rerender } = render(<RightPanel spec={null} onSelect={() => {}} onClose={() => {}} />)
    expect(screen.queryByRole('button', { name: '회원 관리' })).not.toBeInTheDocument()
    rerender(<RightPanel spec={null} onSelect={() => {}} onClose={() => {}} isAdmin />)
    expect(screen.getByRole('button', { name: '회원 관리' })).toBeInTheDocument()
  })

  it('회원 관리 → {kind:admin}, admin body 에 currentUserId 전달', () => {
    const onSelect = vi.fn()
    render(<RightPanel spec={null} onSelect={onSelect} onClose={() => {}} isAdmin currentUserId={7} />)
    fireEvent.click(screen.getByRole('button', { name: '회원 관리' }))
    expect(onSelect).toHaveBeenCalledWith({ kind: 'admin', args: {}, valid: true })
    // spec 이 admin 이면 AdminPanel 을 렌더하고 currentUserId 를 넘긴다.
    render(<RightPanel spec={spec({ kind: 'admin' })} onSelect={() => {}} onClose={() => {}} isAdmin currentUserId={7} />)
    expect(screen.getByTestId('admin')).toHaveTextContent('admin:7')
  })

  it('종목검색: 유효 ticker 제출 → {kind:stock_report, args:{ticker}}', () => {
    const onSelect = vi.fn()
    render(<RightPanel spec={null} onSelect={onSelect} onClose={() => {}} />)
    const input = screen.getByLabelText('종목 검색')
    fireEvent.change(input, { target: { value: '005930' } })
    fireEvent.submit(input.closest('form'))
    expect(onSelect).toHaveBeenCalledWith({ kind: 'stock_report', args: { ticker: '005930' }, valid: true })
  })

  it('종목검색: 불량 ticker 제출 → onSelect 미호출(isValidTicker SSOT)', () => {
    const onSelect = vi.fn()
    render(<RightPanel spec={null} onSelect={onSelect} onClose={() => {}} />)
    const input = screen.getByLabelText('종목 검색')
    fireEvent.change(input, { target: { value: '삼성' } }) // 6자 영숫자 아님
    fireEvent.submit(input.closest('form'))
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('종목검색: 불량 ticker 제출 → 능동 안내 메시지 노출(무한 침묵 금지)', () => {
    // 기존엔 조회만 무시하고 아무 피드백이 없어 "왜 안 되지?" 여지가 있었다(UX 개선).
    // 이제 형식 불량이면 짧은 안내를 띄운다 — 조회는 여전히 안 함(isValidTicker SSOT 유지).
    const onSelect = vi.fn()
    render(<RightPanel spec={null} onSelect={onSelect} onClose={() => {}} />)
    const input = screen.getByLabelText('종목 검색')
    fireEvent.change(input, { target: { value: '123' } }) // 6자리 아님
    fireEvent.submit(input.closest('form'))
    expect(onSelect).not.toHaveBeenCalled() // 조회 없음(잘못된 백엔드 조회 방지) — 기존 계약 유지
    expect(screen.getByRole('alert')).toHaveTextContent(/6자리/) // 능동 안내
  })

  it('종목검색: 불량 안내 후 다시 입력하면 안내가 사라진다(자기치유)', () => {
    render(<RightPanel spec={null} onSelect={() => {}} onClose={() => {}} />)
    const input = screen.getByLabelText('종목 검색')
    fireEvent.change(input, { target: { value: '123' } })
    fireEvent.submit(input.closest('form'))
    expect(screen.queryByRole('alert')).toBeInTheDocument()
    fireEvent.change(input, { target: { value: '005930' } }) // 다시 타이핑 → 안내 해제
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('종목검색: 유효 ticker 제출은 안내를 남기지 않는다', () => {
    const onSelect = vi.fn()
    render(<RightPanel spec={null} onSelect={onSelect} onClose={() => {}} />)
    const input = screen.getByLabelText('종목 검색')
    fireEvent.change(input, { target: { value: '005930' } })
    fireEvent.submit(input.closest('form'))
    expect(onSelect).toHaveBeenCalled()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('활성 kind 의 퀵버튼에 활성 표시(aria-pressed) — 현재 위치 파랑/주황 강조', () => {
    render(<RightPanel spec={spec({ kind: 'watchlist' })} onSelect={() => {}} onClose={() => {}} />)
    expect(screen.getByRole('button', { name: '관심종목' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '시장 국면' })).toHaveAttribute('aria-pressed', 'false')
  })
})

// ── 종목명 자동완성 원복(항목6) — 이름으로 검색 → 후보 선택 → 조회 ──
describe('RightPanel 종목검색 자동완성', () => {
  it('종목명 입력 → 디바운스 검색 → 후보 드롭다운 → 선택 시 onSelect(stock_report+종목명)', async () => {
    searchStocks.mockResolvedValue([
      { ticker: '005930', name: '삼성전자', market: 'KOSPI' },
      { ticker: '005935', name: '삼성전자우', market: 'KOSPI' },
    ])
    const onSelect = vi.fn()
    render(<RightPanel spec={null} onSelect={onSelect} onClose={() => {}} />)
    const input = screen.getByLabelText('종목 검색')
    fireEvent.change(input, { target: { value: '삼성' } })
    // 180ms 디바운스 후 검색·드롭다운.
    const option = await screen.findByText('삼성전자')
    await waitFor(() => expect(searchStocks).toHaveBeenCalledWith('삼성', 8))
    expect(screen.getByRole('listbox')).toBeInTheDocument()
    fireEvent.mouseDown(option) // 후보 선택
    expect(onSelect).toHaveBeenCalledWith({
      kind: 'stock_report',
      args: { ticker: '005930', stock_name: '삼성전자' },
      valid: true,
    })
  })

  it('종목명인데 후보 없음 + 제출 → 안내만(잘못된 조회 방지, onSelect 미호출)', async () => {
    searchStocks.mockResolvedValue([])
    const onSelect = vi.fn()
    render(<RightPanel spec={null} onSelect={onSelect} onClose={() => {}} />)
    const input = screen.getByLabelText('종목 검색')
    fireEvent.change(input, { target: { value: '없는종목명' } })
    fireEvent.submit(input.closest('form'))
    expect(onSelect).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('키보드: ↓ 로 후보 활성 후 Enter 제출 → 활성 후보로 조회', async () => {
    searchStocks.mockResolvedValue([
      { ticker: '000660', name: 'SK하이닉스', market: 'KOSPI' },
      { ticker: '005930', name: '삼성전자', market: 'KOSPI' },
    ])
    const onSelect = vi.fn()
    render(<RightPanel spec={null} onSelect={onSelect} onClose={() => {}} />)
    const input = screen.getByLabelText('종목 검색')
    fireEvent.change(input, { target: { value: '하이' } })
    await screen.findByText('SK하이닉스')
    fireEvent.keyDown(input, { key: 'ArrowDown' }) // 첫 후보 활성
    fireEvent.submit(input.closest('form'))
    expect(onSelect).toHaveBeenCalledWith({
      kind: 'stock_report',
      args: { ticker: '000660', stock_name: 'SK하이닉스' },
      valid: true,
    })
  })
})
