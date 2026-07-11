import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
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
vi.mock('./RegimeGauge.jsx', () => ({
  default: () => <div data-testid="regime-gauge">regime-gauge</div>,
}))
vi.mock('./PopupWatchlist.jsx', () => ({
  default: ({ args }) => <div data-testid="watchlist">watchlist:{args?.sort_by ?? ''}</div>,
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
  default: () => <div data-testid="balance">balance</div>,
}))

const spec = (o) => ({ args: {}, valid: true, ...o })

beforeEach(() => vi.clearAllMocks())

describe('RightPanel 본문 라우팅(spec.kind → 인라인 컴포넌트)', () => {
  it('watchlist → PopupWatchlist(랜딩 기본)', () => {
    render(<RightPanel spec={spec({ kind: 'watchlist', args: { sort_by: 'change' } })} onSelect={() => {}} onClose={() => {}} />)
    expect(screen.getByTestId('watchlist')).toHaveTextContent('watchlist:change')
  })

  it('macro_dashboard → RegimeGauge', () => {
    render(<RightPanel spec={spec({ kind: 'macro_dashboard' })} onSelect={() => {}} onClose={() => {}} />)
    expect(screen.getByTestId('regime-gauge')).toBeInTheDocument()
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

  it('종목검색: 유효 ticker 제출 → {kind:stock_report, args:{ticker}}', () => {
    const onSelect = vi.fn()
    render(<RightPanel spec={null} onSelect={onSelect} onClose={() => {}} />)
    const input = screen.getByLabelText('종목코드 입력')
    fireEvent.change(input, { target: { value: '005930' } })
    fireEvent.submit(input.closest('form'))
    expect(onSelect).toHaveBeenCalledWith({ kind: 'stock_report', args: { ticker: '005930' }, valid: true })
  })

  it('종목검색: 불량 ticker 제출 → onSelect 미호출(isValidTicker SSOT)', () => {
    const onSelect = vi.fn()
    render(<RightPanel spec={null} onSelect={onSelect} onClose={() => {}} />)
    const input = screen.getByLabelText('종목코드 입력')
    fireEvent.change(input, { target: { value: '삼성' } }) // 6자 영숫자 아님
    fireEvent.submit(input.closest('form'))
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('종목검색: 불량 ticker 제출 → 능동 안내 메시지 노출(무한 침묵 금지)', () => {
    // 기존엔 조회만 무시하고 아무 피드백이 없어 "왜 안 되지?" 여지가 있었다(UX 개선).
    // 이제 형식 불량이면 짧은 안내를 띄운다 — 조회는 여전히 안 함(isValidTicker SSOT 유지).
    const onSelect = vi.fn()
    render(<RightPanel spec={null} onSelect={onSelect} onClose={() => {}} />)
    const input = screen.getByLabelText('종목코드 입력')
    fireEvent.change(input, { target: { value: '123' } }) // 6자리 아님
    fireEvent.submit(input.closest('form'))
    expect(onSelect).not.toHaveBeenCalled() // 조회 없음(잘못된 백엔드 조회 방지) — 기존 계약 유지
    expect(screen.getByRole('alert')).toHaveTextContent(/6자리/) // 능동 안내
  })

  it('종목검색: 불량 안내 후 다시 입력하면 안내가 사라진다(자기치유)', () => {
    render(<RightPanel spec={null} onSelect={() => {}} onClose={() => {}} />)
    const input = screen.getByLabelText('종목코드 입력')
    fireEvent.change(input, { target: { value: '123' } })
    fireEvent.submit(input.closest('form'))
    expect(screen.queryByRole('alert')).toBeInTheDocument()
    fireEvent.change(input, { target: { value: '005930' } }) // 다시 타이핑 → 안내 해제
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('종목검색: 유효 ticker 제출은 안내를 남기지 않는다', () => {
    const onSelect = vi.fn()
    render(<RightPanel spec={null} onSelect={onSelect} onClose={() => {}} />)
    const input = screen.getByLabelText('종목코드 입력')
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
