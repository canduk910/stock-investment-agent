import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import AnalystReportsSection from './AnalystReportsSection.jsx'

// 애널리스트 리포트 요약 섹션 렌더 스모크(jsdom) — 경계(api.js)만 mock, 렌더·상담 콜백 로직은 실제 통과.
//   요약은 '리포트 내용 인용'(출처 귀속)·면책 상시 · "이 리포트로 상담하기"→setReportContext→onConsult.

vi.mock('../api.js', () => ({
  fetchAnalystReports: vi.fn(),
  fetchNaverStockReports: vi.fn(),
  setReportContext: vi.fn(),
}))
import { fetchAnalystReports, fetchNaverStockReports, setReportContext } from '../api.js'

const REPORT = {
  report_id: '94082',
  broker: '한화투자증권',
  stock_name: 'GS건설',
  title: '확실한 투자포인트',
  date: '26.07.10',
  pdf_url: 'https://stock.pstatic.net/x/94082.pdf',
  summary: {
    증권사: '한화투자증권', 종목: 'GS건설', 목표주가: '5만원', 투자의견: '매수',
    요약: '건설 실적 개선 기대.', 핵심요지: ['수주 회복', '마진 개선'],
    리스크요인: ['원자재 가격 변동'], 면책고지: '이 요약은 리포트 내용이며 자문이 아니다.',
  },
}

beforeEach(() => {
  fetchAnalystReports.mockReset()
  fetchNaverStockReports.mockReset()
  setReportContext.mockReset()
})

describe('AnalystReportsSection 렌더', () => {
  it('저장된 리포트 요약 카드를 렌더(출처 귀속·목표주가·핵심요지·리스크·면책)', async () => {
    fetchAnalystReports.mockResolvedValue({ ticker: '006360', reports: [REPORT] })
    render(<AnalystReportsSection ticker="006360" sessionId="s1" onConsult={() => {}} />)
    await waitFor(() => expect(screen.getByText('한화투자증권')).toBeInTheDocument())
    expect(screen.getByText(/목표주가 5만원/)).toBeInTheDocument()
    // 투자의견은 '리포트 의견'으로 출처 귀속 표기(에이전트 판정 아님).
    expect(screen.getByText(/리포트 의견 · 매수/)).toBeInTheDocument()
    expect(screen.getByText('수주 회복')).toBeInTheDocument()
    expect(screen.getByText('원자재 가격 변동')).toBeInTheDocument()
    // 면책 상시(카드 면책 + 섹션 면책 둘 다) — 최소 1개 이상 노출.
    expect(screen.getAllByText(/자문/).length).toBeGreaterThan(0)
  })

  it('저장된 리포트가 없으면 빈 상태 안내', async () => {
    fetchAnalystReports.mockResolvedValue({ ticker: '006360', reports: [] })
    render(<AnalystReportsSection ticker="006360" sessionId="s1" onConsult={() => {}} />)
    await waitFor(() =>
      expect(screen.getByText(/아직 저장된 애널리스트 리포트가 없어요/)).toBeInTheDocument(),
    )
  })

  it('"이 종목 리포트 가져오기" → fetchNaverStockReports(ticker) 후 재조회', async () => {
    fetchAnalystReports
      .mockResolvedValueOnce({ ticker: '006360', reports: [] })
      .mockResolvedValueOnce({ ticker: '006360', reports: [REPORT] })
    fetchNaverStockReports.mockResolvedValue({ fetched: 3, new: 1, skipped: 2, failed: 0 })
    render(<AnalystReportsSection ticker="006360" sessionId="s1" onConsult={() => {}} />)
    const btn = () => screen.getByRole('button', { name: /이 종목 리포트 가져오기/ })
    await waitFor(btn)
    fireEvent.click(btn())
    // 전체 최신 피드가 아니라 이 종목(006360)으로 수집한다.
    await waitFor(() => expect(fetchNaverStockReports).toHaveBeenCalledWith('006360', 10))
    // 재조회로 새 리포트가 표시된다.
    await waitFor(() => expect(screen.getByText('한화투자증권')).toBeInTheDocument())
  })

  it('"이 리포트로 상담하기" → setReportContext(sessionId,ticker,reportId) + onConsult(broker)', async () => {
    fetchAnalystReports.mockResolvedValue({ ticker: '006360', reports: [REPORT] })
    setReportContext.mockResolvedValue({ ok: true, set: true, broker: '한화투자증권' })
    const onConsult = vi.fn()
    render(<AnalystReportsSection ticker="006360" sessionId="s1" onConsult={onConsult} />)
    await waitFor(() => screen.getByText('이 리포트로 상담하기'))
    fireEvent.click(screen.getByText('이 리포트로 상담하기'))
    await waitFor(() =>
      expect(setReportContext).toHaveBeenCalledWith('s1', '006360', '94082'),
    )
    await waitFor(() => expect(onConsult).toHaveBeenCalledWith('한화투자증권'))
    // 성공 후 버튼은 '불러옴' 확정 표시.
    expect(screen.getByText(/불러옴/)).toBeInTheDocument()
  })

  it('sessionId 없으면 상담 버튼 비활성(세션 없음 안내)', async () => {
    fetchAnalystReports.mockResolvedValue({ ticker: '006360', reports: [REPORT] })
    render(<AnalystReportsSection ticker="006360" sessionId={null} onConsult={() => {}} />)
    await waitFor(() => screen.getByText('이 리포트로 상담하기'))
    expect(screen.getByText('이 리포트로 상담하기')).toBeDisabled()
  })
})
