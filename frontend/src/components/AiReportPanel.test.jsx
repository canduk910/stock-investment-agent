import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import AiReportPanel from './AiReportPanel.jsx'

// 컴포넌트 렌더 스모크(IMP-17) — 생성 API 만 mock. 폴백·구조화 렌더·코드고정 면책을 검증.
vi.mock('../api.js', () => ({
  generateStockReport: vi.fn(),
  fetchReportHistory: vi.fn(() => Promise.resolve({ history: [] })),
}))
import { generateStockReport } from '../api.js'

beforeEach(() => generateStockReport.mockReset())

describe('AiReportPanel 렌더 스모크(IMP-17)', () => {
  it('코드고정 면책은 리포트 생성 전에도 항상 노출(자족)', () => {
    render(<AiReportPanel ticker="005930" />)
    expect(screen.getByText(/면허 있는 투자자문·매매 권유가 아닙니다/)).toBeInTheDocument()
  })

  it('validation_failed → 폴백 안내(정량요약 참고)', async () => {
    generateStockReport.mockResolvedValue({
      report: null, validation_failed: true, message: 'AI 서술 생성 실패 — 정량 요약 참고',
    })
    render(<AiReportPanel ticker="005930" />)
    fireEvent.click(screen.getByRole('button', { name: 'AI 리포트 생성' }))
    await waitFor(() => expect(screen.getByText(/AI 서술 생성 실패/)).toBeInTheDocument())
  })

  it('정상 리포트 → 종합의견 배지 + 리스크 요인 렌더', async () => {
    generateStockReport.mockResolvedValue({
      report: {
        종합의견: '신중', 요약: '요약본', 투자포인트: ['성장'], 리스크요인: ['밸류 부담'],
        국면정합성: '정합', 면책고지: '참고용',
      },
      validation_failed: false, regime_at_creation: '확장', created_at: '2026-01-01T00:00:00Z',
    })
    render(<AiReportPanel ticker="005930" />)
    fireEvent.click(screen.getByRole('button', { name: 'AI 리포트 생성' }))
    await waitFor(() => expect(screen.getByText('신중')).toBeInTheDocument())
    expect(screen.getByText('밸류 부담')).toBeInTheDocument()
    expect(screen.getByText('리스크 요인')).toBeInTheDocument()
  })
})
