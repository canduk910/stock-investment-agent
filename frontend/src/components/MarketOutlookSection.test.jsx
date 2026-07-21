import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import MarketOutlookSection from './MarketOutlookSection.jsx'

// 시황 요약 섹션 = **controlled 카드 뷰**(reports·수집상태를 상위 MacroDashboard 가 주입). 자체 fetch·
// 자동 최신화·금일의 요약은 컨테이너로 이관 → 여기선 표시·오버레이·상담만 검증. 요약은 리포트 인용·면책.
// api.js 는 상담(setMarketOutlookContext)만 호출한다.

vi.mock('../api.js', () => ({
  setMarketOutlookContext: vi.fn(),
}))
import { setMarketOutlookContext } from '../api.js'

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
  setMarketOutlookContext.mockReset()
  setMarketOutlookContext.mockResolvedValue({ ok: true, set: true, broker: 'KB증권' })
})

describe('MarketOutlookSection(controlled) 렌더(항목4: 일별·3줄·오버레이)', () => {
  it('컴팩트 카드 = 증권사·시장전망·제목·3줄요약(세줄요약 우선), 상세는 클릭 전 숨김', async () => {
    render(<MarketOutlookSection reports={[REPORT]} />)
    expect(screen.getByText('KB증권')).toBeInTheDocument()
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

  it('상세 오버레이 "이 시황으로 상담하기" → setMarketOutlookContext(sessionId, report_id) + onConsult + 닫힘', async () => {
    const onConsult = vi.fn()
    render(<MarketOutlookSection reports={[REPORT]} sessionId="99" onConsult={onConsult} />)
    fireEvent.click(screen.getByText('7/10 모닝코멘트'))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByText('이 시황으로 상담하기'))
    await waitFor(() => expect(setMarketOutlookContext).toHaveBeenCalledWith('99', '36722'))
    await waitFor(() => expect(onConsult).toHaveBeenCalledWith('KB증권'))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull()) // 상담 시작 후 오버레이 닫힘
  })

  it('sessionId 없으면 상담 버튼 비활성 / onConsult 미전달이면 버튼 없음(옵셔널)', async () => {
    const { rerender } = render(<MarketOutlookSection reports={[REPORT]} onConsult={vi.fn()} />)
    fireEvent.click(screen.getByText('7/10 모닝코멘트'))
    let dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('이 시황으로 상담하기')).toBeDisabled() // sessionId 없음
    fireEvent.click(within(dialog).getByLabelText('닫기'))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    // onConsult 미전달 → 버튼 자체 없음
    rerender(<MarketOutlookSection reports={[REPORT]} />)
    fireEvent.click(screen.getByText('7/10 모닝코멘트'))
    dialog = await screen.findByRole('dialog')
    expect(within(dialog).queryByText('이 시황으로 상담하기')).toBeNull()
  })

  it('세줄요약 없는 구 레코드 → 핵심요지 최대 3개로 폴백', async () => {
    render(<MarketOutlookSection reports={[REPORT_OLD]} />)
    expect(screen.getByText('삼성증권')).toBeInTheDocument()
    expect(screen.getByText('금리 부담')).toBeInTheDocument()
    expect(screen.getByText('실적 하향')).toBeInTheDocument()
    expect(screen.queryByText('4번째')).toBeNull() // 3개 상한
  })

  it('작성일별 그룹 헤더로 구분', async () => {
    render(<MarketOutlookSection reports={[REPORT, REPORT_OLD]} />)
    expect(screen.getByText('KB증권')).toBeInTheDocument()
    expect(screen.getByText('26.07.10')).toBeInTheDocument()
    expect(screen.getByText('26.07.08')).toBeInTheDocument()
  })

  it('카드 클릭 → 상세 오버레이(요약·핵심요지·리스크·면책·PDF), ✕·Esc 닫힘', async () => {
    render(<MarketOutlookSection reports={[REPORT]} />)
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
    render(<MarketOutlookSection reports={[]} />)
    expect(screen.getByText(/아직 저장된 시황 리포트가 없어요/)).toBeInTheDocument()
  })

  it('"네이버 최신 시황 가져오기" 클릭 → onFetch 콜백 호출(수집은 컨테이너 소유)', async () => {
    const onFetch = vi.fn()
    render(<MarketOutlookSection reports={[]} onFetch={onFetch} />)
    fireEvent.click(screen.getByText(/네이버 최신 시황 가져오기/))
    expect(onFetch).toHaveBeenCalled()
  })

  it('loading prop → 조회 중 안내, error prop → 재시도(onReload)', async () => {
    const onReload = vi.fn()
    const { rerender } = render(<MarketOutlookSection reports={null} loading={true} />)
    expect(screen.getByText(/시황 요약 조회 중/)).toBeInTheDocument()
    rerender(<MarketOutlookSection reports={null} loading={false} error="네트워크 오류" onReload={onReload} />)
    expect(screen.getByText(/시황 조회 실패: 네트워크 오류/)).toBeInTheDocument()
    fireEvent.click(screen.getByText(/재시도/))
    expect(onReload).toHaveBeenCalled()
  })

  it('fetching prop → 진행바, fetchMsg·autoNote prop → 안내 표시', async () => {
    render(
      <MarketOutlookSection
        reports={[REPORT]}
        fetching={true}
        progress={{ stage: 'list', reports: [], done: 0, total: 0 }}
        fetchMsg="새 요약 1건 · 확인 1건"
        autoNote="오늘 최신 시황을 자동으로 확인하는 중…"
      />,
    )
    expect(screen.getByText(/오늘 최신 시황을 자동으로 확인하는 중/)).toBeInTheDocument()
    expect(screen.getByText(/새 요약 1건/)).toBeInTheDocument()
    // 가져오기 버튼은 fetching 중 비활성.
    expect(screen.getByText('가져오는 중…')).toBeDisabled()
  })
})
