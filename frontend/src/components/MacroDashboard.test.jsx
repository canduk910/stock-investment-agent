import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import MacroDashboard from './MacroDashboard.jsx'

// 시장국면 대시보드 컨테이너 = 시황 lifecycle(수집·요약) 단일 소유. 검증 포인트:
//   ① 레이아웃 순서(금일의 요약 → 국면 판정 → 증권사 시황 카드)
//   ② [네이버 최신 시황 가져오기 → 요약 생성] 순차 자동 오케스트레이션
//   ③ 하루 1회 가드(자동수집·자동요약 폭주 방지, 재오픈 캐시 재사용)
// 시황 요약은 리포트 인용·면책, 시장 판정은 코드(RegimeGauge=엔진, 여기선 stub).

vi.mock('../api.js', () => ({
  fetchMarketOutlook: vi.fn(),
  fetchNaverMarketOutlook: vi.fn(),
  streamFetchMarketOutlook: vi.fn(),
  fetchMarketOutlookSummary: vi.fn(),
  setMarketOutlookContext: vi.fn(), // MarketOutlookSection(상담) 경계
}))
import {
  fetchMarketOutlook,
  streamFetchMarketOutlook,
  fetchMarketOutlookSummary,
} from '../api.js'
import { todayStampKST } from '../lib/marketOutlook.js' // 실제 헬퍼(모킹 안 함)

// RegimeGauge 는 자체 조회(fetchMacroRegime 등)라 무겁다 — 이 테스트는 컨테이너 오케스트레이션이 관심사이므로 stub.
vi.mock('./RegimeGauge.jsx', () => ({ default: () => <div data-testid="regime-gauge">국면 게이지</div> }))

// jsdom 에 localStorage 전역이 없어(auth.test 선례) 인메모리 스텁 — 자동수집·요약 가드/캐시 검증용.
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

const SUMMARY_RES = {
  validation_failed: false,
  report_count: 5,
  summary: {
    시장전망분포: '중립 3·신중 2',
    종합요약: ['외국인 수급 개선', '실적 시즌 기대', '환율 변동성 유의'],
    면책고지: '이 종합은 여러 증권사 시황 리포트 내용이며 자문이 아니다.',
  },
}

function report(date) {
  return {
    report_id: '36722',
    broker: 'KB증권',
    title: '모닝코멘트',
    date,
    summary: { 증권사: 'KB증권', 제목: '모닝코멘트', 시장전망: '중립', 세줄요약: ['a', 'b', 'c'], 면책고지: '자문 아님.' },
  }
}

beforeEach(() => {
  fetchMarketOutlook.mockReset()
  streamFetchMarketOutlook.mockReset()
  streamFetchMarketOutlook.mockResolvedValue(undefined)
  fetchMarketOutlookSummary.mockReset()
  fetchMarketOutlookSummary.mockResolvedValue(SUMMARY_RES)
  localStorage.clear()
})

describe('MacroDashboard 오케스트레이션', () => {
  it('레이아웃 순서: 금일의 요약(최상단) → 국면 판정 → 증권사 시황 카드', async () => {
    localStorage.setItem('mo_autofetch_date', todayStampKST()) // 자동수집 억제
    fetchMarketOutlook.mockResolvedValue({ reports: [report(todayStampKST())] })
    render(<MacroDashboard />)
    // 오늘자(stale 아님) → 캐시 없음 → 자동 요약 1회 생성.
    await waitFor(() => expect(fetchMarketOutlookSummary).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByText('금일의 요약')).toBeInTheDocument())

    const daily = screen.getByText('금일의 요약')
    const gauge = screen.getByTestId('regime-gauge')
    const outlook = screen.getByText('증권사 시황 리포트 요약')
    // DOM 순서: 금일의 요약 → 국면 게이지 → 증권사 시황 카드.
    expect(daily.compareDocumentPosition(gauge) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(gauge.compareDocumentPosition(outlook) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('저장 시황이 오늘자(최신) → 자동 수집 안 하고 곧바로 금일의 요약 자동 생성', async () => {
    localStorage.setItem('mo_autofetch_date', todayStampKST())
    fetchMarketOutlook.mockResolvedValue({ reports: [report(todayStampKST())] })
    render(<MacroDashboard />)
    await waitFor(() => expect(fetchMarketOutlookSummary).toHaveBeenCalledTimes(1))
    expect(streamFetchMarketOutlook).not.toHaveBeenCalled() // 이미 최신 → 수집 불필요
    await waitFor(() => expect(screen.getByText('외국인 수급 개선')).toBeInTheDocument())
  })

  it('stale(오래된 시황) → [자동 수집 → 요약 생성] 순차 실행', async () => {
    // 가드 없음(자동수집 허용). 첫 조회는 오래된 것, 수집 후 재조회는 오늘자.
    fetchMarketOutlook
      .mockResolvedValueOnce({ reports: [report('20.01.01')] })
      .mockResolvedValueOnce({ reports: [report(todayStampKST())] })
    streamFetchMarketOutlook.mockImplementation(async ({ onEvent }) => {
      onEvent({ type: 'done', fetched: 1, new: 1, skipped: 0, failed: 0 })
    })
    render(<MacroDashboard />)
    await waitFor(() => expect(streamFetchMarketOutlook).toHaveBeenCalled()) // 자동 수집
    await waitFor(() => expect(fetchMarketOutlookSummary).toHaveBeenCalled()) // 수집 후 요약
    expect(localStorage.getItem('mo_autofetch_date')).toBe(todayStampKST()) // 가드 세팅(폭주 방지)
    await waitFor(() => expect(screen.getByText('외국인 수급 개선')).toBeInTheDocument())
  })

  it('재오픈: 오늘 이미 생성한 요약 캐시가 있으면 재사용(LLM 재호출 없음)', async () => {
    localStorage.setItem('mo_autofetch_date', todayStampKST())
    localStorage.setItem('mo_daily_summary', JSON.stringify({ date: todayStampKST(), res: SUMMARY_RES }))
    fetchMarketOutlook.mockResolvedValue({ reports: [report(todayStampKST())] })
    render(<MacroDashboard />)
    // 캐시된 요약이 즉시 표시되고, 생성 API 는 호출하지 않는다.
    await waitFor(() => expect(screen.getByText('외국인 수급 개선')).toBeInTheDocument())
    expect(fetchMarketOutlookSummary).not.toHaveBeenCalled()
  })

  it('저장 시황이 비었고 오늘 이미 자동수집 시도함 → 요약 미생성·금일의 요약 카드 미노출', async () => {
    localStorage.setItem('mo_autofetch_date', todayStampKST()) // 재수집 억제
    fetchMarketOutlook.mockResolvedValue({ reports: [] })
    render(<MacroDashboard />)
    await waitFor(() => expect(fetchMarketOutlook).toHaveBeenCalled())
    // 시황 0개 → 요약 생성 안 함, 금일의 요약 카드도 안 뜸.
    expect(fetchMarketOutlookSummary).not.toHaveBeenCalled()
    expect(screen.queryByText('금일의 요약')).toBeNull()
    // 대신 빈 상태 안내가 뜬다(컨트롤드 MarketOutlookSection).
    expect(screen.getByText(/아직 저장된 시황 리포트가 없어요/)).toBeInTheDocument()
  })

  it('요약 생성 실패(validation_failed) → 에러 안내(무한 스피너 금지)', async () => {
    localStorage.setItem('mo_autofetch_date', todayStampKST())
    fetchMarketOutlook.mockResolvedValue({ reports: [report(todayStampKST())] })
    fetchMarketOutlookSummary.mockResolvedValue({ validation_failed: true, message: '요약 생성 실패' })
    render(<MacroDashboard />)
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/요약 생성 실패/))
  })

  it('초기 조회가 백엔드 장애로 실패 → 자동 최신화 스킵(진행바+에러 동시표시 방지), 에러+재시도만', async () => {
    localStorage.clear() // 가드 해제(자동수집 허용 조건) — 그럼에도 load 실패면 트리거 안 해야 한다.
    fetchMarketOutlook.mockRejectedValue(new Error('서버 오류'))
    render(<MacroDashboard />)
    await waitFor(() => expect(screen.getByText(/시황 조회 실패: 서버 오류/)).toBeInTheDocument())
    // 백엔드 장애에서는 자동 수집(SSE)·자동 요약을 걸지 않는다(헛수집·이중 배너 방지).
    expect(streamFetchMarketOutlook).not.toHaveBeenCalled()
    expect(fetchMarketOutlookSummary).not.toHaveBeenCalled()
    // '가져오는 중…' 진행 안내가 에러와 함께 뜨지 않는다.
    expect(screen.queryByText('가져오는 중…')).toBeNull()
  })
})
