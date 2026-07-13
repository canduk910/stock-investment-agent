import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import MarketOutlookSection from './MarketOutlookSection.jsx'

// 시황 요약 섹션 렌더 스모크(jsdom) — 경계(api.js)만 mock. 요약은 '시황 리포트 인용'·면책 상시.
// 항목4: 일별 구분 + 컴팩트 3줄요약 카드 + 클릭 시 상세 오버레이(딤 배경·Esc/✕ 닫힘).

vi.mock('../api.js', () => ({
  fetchMarketOutlook: vi.fn(),
  fetchNaverMarketOutlook: vi.fn(),
  streamFetchMarketOutlook: vi.fn(),
}))
import { fetchMarketOutlook, fetchNaverMarketOutlook, streamFetchMarketOutlook } from '../api.js'
import { todayStampKST } from '../lib/marketOutlook.js' // 실제 헬퍼(모킹 안 함)

// jsdom 환경에 localStorage 전역이 없어(auth.test.js 선례) 인메모리로 스텁 — 자동수집 가드 검증용.
const _ls = {}
vi.stubGlobal('localStorage', {
  getItem: (k) => (k in _ls ? _ls[k] : null),
  setItem: (k, v) => {
    _ls[k] = String(v)
  },
  removeItem: (k) => {
    delete _ls[k]
  },
  clear: () => {
    for (const k of Object.keys(_ls)) delete _ls[k]
  },
})

const REPORT = {
  report_id: '36722',
  broker: 'KB증권',
  title: '7/10 모닝코멘트',
  date: '26.07.10',
  pdf_url: 'https://stock.pstatic.net/market/x.pdf',
  summary: {
    증권사: 'KB증권', 제목: '7/10 모닝코멘트', 시장전망: '중립',
    요약: '수급 개선 기대.', 세줄요약: ['외국인 순매수 전환', '실적 시즌 기대', '환율은 변수'],
    핵심요지: ['외국인 순매수'], 리스크요인: ['환율 변동성'],
    면책고지: '이 요약은 시황 리포트 내용이며 자문이 아니다.',
  },
}

// 구 레코드(세줄요약 없음) — 핵심요지 폴백 확인용.
const REPORT_OLD = {
  report_id: '36700',
  broker: '삼성증권',
  title: '7/8 데일리',
  date: '26.07.08',
  summary: {
    증권사: '삼성증권', 제목: '7/8 데일리', 시장전망: '신중',
    요약: '변동성 확대.', 핵심요지: ['금리 부담', '수급 약화', '실적 하향', '4번째'],
    리스크요인: ['긴축'], 면책고지: '자문 아님.',
  },
}

beforeEach(() => {
  fetchMarketOutlook.mockReset()
  fetchNaverMarketOutlook.mockReset()
  streamFetchMarketOutlook.mockReset()
  streamFetchMarketOutlook.mockResolvedValue(undefined) // 자동수집이 우발적으로 fire해도 안전
  // 기존 테스트는 자동 최신화를 억제(가드=오늘) — 자동수집 테스트만 가드를 해제/조작한다.
  localStorage.clear()
  localStorage.setItem('mo_autofetch_date', todayStampKST())
})

describe('MarketOutlookSection 렌더(항목4: 일별·3줄·오버레이)', () => {
  it('컴팩트 카드 = 증권사·시장전망·제목·3줄요약(세줄요약 우선), 상세는 클릭 전 숨김', async () => {
    fetchMarketOutlook.mockResolvedValue({ reports: [REPORT] })
    render(<MarketOutlookSection />)
    await waitFor(() => expect(screen.getByText('KB증권')).toBeInTheDocument())
    expect(screen.getByText(/시장전망 · 중립/)).toBeInTheDocument()
    // 3줄요약(세줄요약) 표시.
    expect(screen.getByText('외국인 순매수 전환')).toBeInTheDocument()
    expect(screen.getByText('환율은 변수')).toBeInTheDocument()
    // 상세(리스크요인·전체 요약)는 클릭 전엔 보이지 않는다.
    expect(screen.queryByText('환율 변동성')).toBeNull()
    expect(screen.queryByText(/수급 개선 기대/)).toBeNull()
    // 섹션 면책 상시.
    expect(screen.getAllByText(/자문/).length).toBeGreaterThan(0)
  })

  it('세줄요약 없는 구 레코드 → 핵심요지 최대 3개로 폴백', async () => {
    fetchMarketOutlook.mockResolvedValue({ reports: [REPORT_OLD] })
    render(<MarketOutlookSection />)
    await waitFor(() => expect(screen.getByText('삼성증권')).toBeInTheDocument())
    expect(screen.getByText('금리 부담')).toBeInTheDocument()
    expect(screen.getByText('실적 하향')).toBeInTheDocument()
    expect(screen.queryByText('4번째')).toBeNull() // 3개 상한
  })

  it('작성일별 그룹 헤더로 구분', async () => {
    fetchMarketOutlook.mockResolvedValue({ reports: [REPORT, REPORT_OLD] })
    render(<MarketOutlookSection />)
    await waitFor(() => expect(screen.getByText('KB증권')).toBeInTheDocument())
    expect(screen.getByText('26.07.10')).toBeInTheDocument()
    expect(screen.getByText('26.07.08')).toBeInTheDocument()
  })

  it('카드 클릭 → 상세 오버레이(요약·핵심요지·리스크·면책·PDF), ✕·Esc 닫힘', async () => {
    fetchMarketOutlook.mockResolvedValue({ reports: [REPORT] })
    render(<MarketOutlookSection />)
    await waitFor(() => expect(screen.getByText('KB증권')).toBeInTheDocument())

    fireEvent.click(screen.getByText('7/10 모닝코멘트'))
    const dialog = await screen.findByRole('dialog')
    const box = within(dialog)
    expect(box.getByText(/수급 개선 기대/)).toBeInTheDocument() // 전체 요약
    expect(box.getByText('외국인 순매수')).toBeInTheDocument() // 핵심요지
    expect(box.getByText('환율 변동성')).toBeInTheDocument() // 리스크요인
    expect(box.getByText(/자문/)).toBeInTheDocument() // 면책
    expect(box.getByText(/원문 PDF/)).toBeInTheDocument() // PDF 링크

    // ✕ 닫힘.
    fireEvent.click(box.getByLabelText('닫기'))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())

    // 다시 열고 Esc 닫힘.
    fireEvent.click(screen.getByText('7/10 모닝코멘트'))
    await screen.findByRole('dialog')
    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
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

describe('시황 자동 최신화 — 패널 로드 시 stale이면 자동 수집', () => {
  it('저장 최신 시황이 오래된 날짜 → 마운트 시 자동 수집 + 안내', async () => {
    localStorage.clear() // 가드 해제 → 자동수집 허용
    fetchMarketOutlook.mockResolvedValue({ reports: [{ ...REPORT_OLD, date: '20.01.01' }] })
    streamFetchMarketOutlook.mockImplementation(async ({ onEvent }) => {
      onEvent({ type: 'done', fetched: 0, new: 0, skipped: 0, failed: 0 })
    })
    render(<MarketOutlookSection />)
    // 클릭 없이(마운트만으로) 자동 수집 트리거.
    await waitFor(() => expect(streamFetchMarketOutlook).toHaveBeenCalled())
    // 가드가 오늘로 세팅됨(중복 방지).
    expect(localStorage.getItem('mo_autofetch_date')).toBe(todayStampKST())
  })

  it('저장 최신 시황이 오늘 → 자동 수집 안 함', async () => {
    localStorage.clear()
    const today = todayStampKST()
    fetchMarketOutlook.mockResolvedValue({ reports: [{ ...REPORT, date: today }] })
    render(<MarketOutlookSection />)
    await waitFor(() => expect(screen.getByText('KB증권')).toBeInTheDocument())
    expect(streamFetchMarketOutlook).not.toHaveBeenCalled() // 오늘자라 자동수집 불필요
  })

  it('오늘 이미 자동수집함(가드) → stale이어도 자동 수집 안 함', async () => {
    localStorage.setItem('mo_autofetch_date', todayStampKST()) // 가드 = 오늘
    fetchMarketOutlook.mockResolvedValue({ reports: [{ ...REPORT_OLD, date: '20.01.01' }] })
    render(<MarketOutlookSection />)
    await waitFor(() => expect(screen.getByText('삼성증권')).toBeInTheDocument())
    expect(streamFetchMarketOutlook).not.toHaveBeenCalled() // 가드로 중복 수집 방지
  })
})
