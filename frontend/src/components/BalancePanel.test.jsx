import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import BalancePanel from './BalancePanel.jsx'

// BalancePanel 렌더 스모크(IMP-17 jsdom) — /api/balance 자체조회 → 요약카드 + 보유종목표.
// 경계(global.fetch)만 mock, 실제 fetchBalance(api.js)·손익 색·부분실패 렌더 로직은 실제 통과.
//   → HTTP 오류 경로도 fetchBalance 의 throw 가 컴포넌트 내부에서 자연 발생(미리 만든 rejected promise
//      가 없어 vitest4+jsdom 의 unhandledRejection 오탐 없음). "경계만 mock" 원칙(tdd-workflow)에도 부합.
// 계약(data-engineer UX2 확정, ux_data_balance.md):
//   {holdings:[{ticker,name,qty,avg_price,current_price,eval_amount,pnl_amount,pnl_pct}],
//    summary:{deposit,purchase_amount,eval_amount,pnl_amount,total_eval,net_asset}, partial_failure:[]}
//   KIS 실패 시: holdings=null, summary=null, partial_failure:['balance'] (항상 200).
// 손익 색 = 글로벌 팔레트(상승=파랑 --c-up / 하락=회색 --c-down) — WatchlistView 등락률과 동일(빨강 금지).

const OK_VIEW = {
  holdings: [
    {
      ticker: '005930', name: '삼성전자', qty: 10, avg_price: 70000,
      current_price: 80000, eval_amount: 800000, pnl_amount: 100000, pnl_pct: 14.28,
    },
    {
      ticker: '000660', name: 'SK하이닉스', qty: 5, avg_price: 130000,
      current_price: 120000, eval_amount: 600000, pnl_amount: -50000, pnl_pct: -7.69,
    },
  ],
  summary: {
    deposit: 500000, purchase_amount: 1350000, eval_amount: 1400000,
    pnl_amount: 50000, total_eval: 1400000, net_asset: 1900000,
  },
  partial_failure: [],
}

// GET /api/balance 200 응답을 반환하는 fetch mock(경계). ok:true + json().
function mockFetchOk(body) {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => body })))
}
// HTTP 오류(백엔드 미연결·5xx) — fetchBalance 가 throw → 컴포넌트 catch → 재시도 UI.
function mockFetchHttpError(status) {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status })))
}

beforeEach(() => vi.restoreAllMocks())
afterEach(() => vi.unstubAllGlobals())

describe('BalancePanel 렌더 스모크(IMP-17)', () => {
  it('요약 카드 + 보유종목 표(종목명·수익/손실) 렌더', async () => {
    mockFetchOk(OK_VIEW)
    render(<BalancePanel />)
    await waitFor(() => expect(screen.getByText('삼성전자')).toBeInTheDocument())
    expect(screen.getByText('SK하이닉스')).toBeInTheDocument()
    // 요약 항목 라벨(예수금·순자산 등)
    expect(screen.getByText(/예수금/)).toBeInTheDocument()
    expect(screen.getByText(/순자산/)).toBeInTheDocument()
    // 면책 상시(리밸런싱 조언 아님)
    expect(screen.getByText(/투자 자문·매매 권유가 아닙니다|정보 제공 목적/)).toBeInTheDocument()
  })

  it('손익 색: 이익=상승(파랑 --c-up)/손실=하락(회색 --c-down) 클래스 — 빨강 금지', async () => {
    mockFetchOk(OK_VIEW)
    const { container } = render(<BalancePanel />)
    await waitFor(() => expect(screen.getByText('삼성전자')).toBeInTheDocument())
    // 방향 클래스가 존재(색 자체는 theme 토큰 CSS). WatchlistView 등락률과 동일 규칙(up/down).
    expect(container.querySelector('.balance__pnl.up')).toBeTruthy() // 삼성전자 +
    expect(container.querySelector('.balance__pnl.down')).toBeTruthy() // 하이닉스 -
    // 빨강(danger) 방향색 오용 없음(손익은 파랑/회색만).
    expect(container.querySelector('.balance__pnl.danger')).toBeFalsy()
  })

  it('부분실패(holdings=null, partial_failure:[balance]) → "일시 조회 불가" 안내(전체 에러 화면 아님)', async () => {
    mockFetchOk({ holdings: null, summary: null, partial_failure: ['balance'] })
    render(<BalancePanel />)
    await waitFor(() =>
      expect(screen.getByText(/일시 조회 불가|불러오지 못|조회할 수 없/)).toBeInTheDocument(),
    )
    // 면책은 부분실패에서도 상시 노출.
    expect(screen.getByText(/투자 자문·매매 권유가 아닙니다|정보 제공 목적/)).toBeInTheDocument()
  })

  it('보유종목 0 → 빈 안내(에러 아님)', async () => {
    mockFetchOk({
      holdings: [],
      summary: { deposit: 500000, purchase_amount: 0, eval_amount: 0, pnl_amount: 0, total_eval: 0, net_asset: 500000 },
      partial_failure: [],
    })
    render(<BalancePanel />)
    await waitFor(() => expect(screen.getByText(/보유 종목이 없습니다/)).toBeInTheDocument())
  })

  it('네트워크/HTTP 오류 → 재시도 버튼(무한 스피너 금지)', async () => {
    mockFetchHttpError(500)
    render(<BalancePanel />)
    await waitFor(() => expect(screen.getByRole('button', { name: /재시도/ })).toBeInTheDocument())
    // 면책은 오류 화면에서도 상시.
    expect(screen.getByText(/투자 자문·매매 권유가 아닙니다|정보 제공 목적/)).toBeInTheDocument()
  })
})
