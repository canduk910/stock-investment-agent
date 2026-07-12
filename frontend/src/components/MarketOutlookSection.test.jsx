import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import MarketOutlookSection from './MarketOutlookSection.jsx'

// 시황 요약 섹션 렌더 스모크(jsdom) — 경계(api.js)만 mock. 요약은 '시황 리포트 인용'·면책 상시.

vi.mock('../api.js', () => ({
  fetchMarketOutlook: vi.fn(),
  fetchNaverMarketOutlook: vi.fn(),
  streamFetchMarketOutlook: vi.fn(),
}))
import { fetchMarketOutlook, fetchNaverMarketOutlook, streamFetchMarketOutlook } from '../api.js'

const REPORT = {
  report_id: '36722',
  broker: 'KB증권',
  title: '7/10 모닝코멘트',
  date: '26.07.10',
  pdf_url: 'https://stock.pstatic.net/market/x.pdf',
  summary: {
    증권사: 'KB증권', 제목: '7/10 모닝코멘트', 시장전망: '중립',
    요약: '수급 개선 기대.', 핵심요지: ['외국인 순매수'],
    리스크요인: ['환율 변동성'], 면책고지: '이 요약은 시황 리포트 내용이며 자문이 아니다.',
  },
}

beforeEach(() => {
  fetchMarketOutlook.mockReset()
  fetchNaverMarketOutlook.mockReset()
  streamFetchMarketOutlook.mockReset()
})

describe('MarketOutlookSection 렌더', () => {
  it('시황 요약 카드 렌더(시장전망·핵심요지·리스크·면책)', async () => {
    fetchMarketOutlook.mockResolvedValue({ reports: [REPORT] })
    render(<MarketOutlookSection />)
    await waitFor(() => expect(screen.getByText('KB증권')).toBeInTheDocument())
    expect(screen.getByText(/시장전망 · 중립/)).toBeInTheDocument()
    expect(screen.getByText('외국인 순매수')).toBeInTheDocument()
    expect(screen.getByText('환율 변동성')).toBeInTheDocument()
    // 면책 상시.
    expect(screen.getAllByText(/자문/).length).toBeGreaterThan(0)
  })

  it('빈 상태 안내', async () => {
    fetchMarketOutlook.mockResolvedValue({ reports: [] })
    render(<MarketOutlookSection />)
    await waitFor(() =>
      expect(screen.getByText(/아직 저장된 시황 리포트가 없어요/)).toBeInTheDocument(),
    )
  })

  it('"네이버 최신 시황 가져오기" → SSE 진행 스트림 후 완료·재조회', async () => {
    fetchMarketOutlook
      .mockResolvedValueOnce({ reports: [] })
      .mockResolvedValueOnce({ reports: [REPORT] })
    streamFetchMarketOutlook.mockImplementation(async ({ onEvent }) => {
      onEvent({ type: 'stage', stage: 'list' })
      onEvent({ type: 'found', reports: [{ id: '36722', broker: 'KB증권', title: '모닝코멘트' }] })
      onEvent({ type: 'progress', id: '36722', result: 'new', done: 1, total: 1 })
      onEvent({ type: 'done', fetched: 1, new: 1, skipped: 0, failed: 0 })
    })
    render(<MarketOutlookSection />)
    await waitFor(() => screen.getByText(/네이버 최신 시황 가져오기/))
    fireEvent.click(screen.getByText(/네이버 최신 시황 가져오기/))
    await waitFor(() => expect(streamFetchMarketOutlook).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByText(/새 요약 1건/)).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText('KB증권')).toBeInTheDocument())
  })
})
