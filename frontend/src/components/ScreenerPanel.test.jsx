import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import ScreenerPanel from './ScreenerPanel.jsx'

// 경계(api.js)만 mock. 전체 유니버스(cached) 렌더 계약 검증:
//   헤더(스캔일 as_of·유니버스 universe_size)·단계 필터·표시 상한·정렬·live 폴백 안내·
//   시장 재조회(cached scope)·클릭 네비·graceful. 캐시 모드엔 현재가/등락/시총이 없어(무캐시)
//   그 표시는 제거됐다 — 카드는 stage 중심(종목명·코드·시장·단계 배지·밴드).

vi.mock('../api.js', () => ({ fetchScreener: vi.fn() }))
import { fetchScreener } from '../api.js'

const CATALOG = {
  periods: { short: 5, medium: 20, long: 40 },
  stages: [
    { stage: 1, name: '안정 상승기', arrangement: '단>중>장', phase: '상승' },
    { stage: 4, name: '안정 하락기', arrangement: '장>중>단', phase: '하락' },
    { stage: 6, name: '상승 진입기', arrangement: '단>장>중', phase: '상승' },
  ],
}

// 전체 보통주 스캔 결과(DB) — 현재가/등락/시총 없음(캐시엔 확정 stage/band만).
function resp(overrides = {}) {
  return {
    // market 은 대문자 "KOSPI"/"KOSDAQ"(stock_master 원값·screener-be 확정), arrangement 는 부등호 양옆 공백.
    candidates: [
      { ticker: '005930', name: '삼성전자', market: 'KOSPI', stage: 4, stage_name: '안정 하락기', arrangement: '장 > 중 > 단', band_width_pct: -16.9, band_direction: '확대', bars_in_stage: 10 },
      { ticker: '207940', name: '삼성바이오로직스', market: 'KOSPI', stage: 1, stage_name: '안정 상승기', arrangement: '단 > 중 > 장', band_width_pct: 2.6, band_direction: '축소', bars_in_stage: 5 },
      { ticker: '000660', name: 'SK하이닉스', market: 'KOSPI', stage: 6, stage_name: '상승 진입기', arrangement: '단 > 장 > 중', band_width_pct: 1.2, band_direction: '확대', bars_in_stage: 2 },
      { ticker: '999999', name: '봉부족주', market: 'KOSDAQ', stage: null, stage_name: null, arrangement: null, band_width_pct: null, band_direction: null, bars_in_stage: 0 },
    ],
    catalog: CATALOG,
    market: 'all',
    scope: 'cached',
    as_of: '2026-08-03',
    total: 4,
    universe_size: 2000,
    partial_failure: [],
    ...overrides,
  }
}

beforeEach(() => {
  fetchScreener.mockReset().mockResolvedValue(resp())
})

describe('ScreenerPanel (전체 유니버스 cached)', () => {
  it('cached 헤더(스캔일·유니버스) 표기 + 상승국면 필터 종목명+단계 배지', async () => {
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText('삼성바이오로직스')).toBeInTheDocument())
    // 헤더: 스캔 기준일 + 전체 보통주 유니버스 크기
    expect(screen.getByText(/2026-08-03/)).toBeInTheDocument()
    expect(screen.getByText(/2,000종목/)).toBeInTheDocument()
    // 상승국면(1·6): 삼성바이오(1)·SK하이닉스(6) 표시, 하락(4) 삼성전자·판정보류(null)는 숨김
    expect(screen.getByText('SK하이닉스')).toBeInTheDocument()
    expect(screen.queryByText('삼성전자')).not.toBeInTheDocument()
    expect(screen.queryByText('봉부족주')).not.toBeInTheDocument()
    // 단계 배지(종목명 + 단계) — catalog 라벨 SSOT
    expect(screen.getByText(/1단계 · 안정 상승기/)).toBeInTheDocument()
    expect(screen.getByText(/6단계 · 상승 진입기/)).toBeInTheDocument()
  })

  it('캐시 모드 — 현재가·등락 칩·시총 미표시(데이터 없음)', async () => {
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText('삼성바이오로직스')).toBeInTheDocument())
    // 캐시엔 시세가 없어 '원'(가격)·'시총' 표기가 사라졌다
    expect(screen.queryByText(/원/)).not.toBeInTheDocument()
    expect(screen.queryByText(/시총/)).not.toBeInTheDocument()
    // 대신 종목코드 + 시장 라벨(대문자 KOSPI → 한글 '코스피' 매핑)이 메타에 표시
    expect(screen.getByText(/207940 · 코스피/)).toBeInTheDocument()
  })

  it("단계 필터 '전체' → 하락 단계·판정보류 종목까지 표시", async () => {
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText('삼성바이오로직스')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: '전체 단계' }))
    await waitFor(() => expect(screen.getByText('삼성전자')).toBeInTheDocument())
    expect(screen.getByText(/4단계 · 안정 하락기/)).toBeInTheDocument()
    expect(screen.getByText('봉부족주')).toBeInTheDocument()
    expect(screen.getByText(/판정 보류/)).toBeInTheDocument()
  })

  it('시장 선택기 → 해당 market·cached scope 로 재조회', async () => {
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText('삼성바이오로직스')).toBeInTheDocument())
    expect(fetchScreener).toHaveBeenCalledWith('all', 'cached')
    fireEvent.click(screen.getByRole('button', { name: '코스닥' }))
    await waitFor(() => expect(fetchScreener).toHaveBeenCalledWith('kosdaq', 'cached'))
  })

  it('시장 선택기에 kospi200 없음(cached 미지원)', async () => {
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText('삼성바이오로직스')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: '전체' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '코스피' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '코스닥' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '코스피200' })).not.toBeInTheDocument()
  })

  it('scope=live 폴백 → 전체 스캔 전 임시 표시 안내', async () => {
    fetchScreener.mockResolvedValue(resp({ scope: 'live', universe_size: 30, as_of: null }))
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText('삼성바이오로직스')).toBeInTheDocument())
    expect(screen.getByText(/전체 스캔 전/)).toBeInTheDocument()
  })

  it('표시 상한 60 초과 → 상위 60만 렌더 + "외 N종목" 카운트(밴드 desc 정렬)', async () => {
    const many = Array.from({ length: 70 }, (_, i) => ({
      ticker: String(100000 + i),
      name: `종목${i}`,
      market: 'KOSPI',
      stage: 1,
      stage_name: '안정 상승기',
      arrangement: '단 > 중 > 장',
      band_width_pct: i, // 0..69 — desc 정렬이면 상위 60 = 종목69..종목10, 숨김 = 종목9..종목0(10개)
      band_direction: '확대',
      bars_in_stage: 3,
    }))
    fetchScreener.mockResolvedValue(resp({ candidates: many, total: 70 }))
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText(/외 10종목/)).toBeInTheDocument())
    // 상위 60개 카드만 렌더(외 10 숨김)
    const rows = screen.getAllByText(/^종목\d+$/)
    expect(rows).toHaveLength(60)
    // band desc: 가장 큰 밴드(종목69) 렌더, 가장 작은(종목0) 숨김
    expect(screen.getByText('종목69')).toBeInTheDocument()
    expect(screen.queryByText('종목0')).not.toBeInTheDocument()
  })

  it('후보 카드 클릭 → onOpenStock(ticker, name)', async () => {
    const onOpenStock = vi.fn()
    render(<ScreenerPanel onOpenStock={onOpenStock} />)
    await waitFor(() => expect(screen.getByText('SK하이닉스')).toBeInTheDocument())
    fireEvent.click(screen.getByText('SK하이닉스'))
    expect(onOpenStock).toHaveBeenCalledWith('000660', 'SK하이닉스')
  })

  it('로딩 상태 표시', async () => {
    let resolve
    fetchScreener.mockReturnValue(new Promise((r) => { resolve = r }))
    render(<ScreenerPanel />)
    expect(screen.getByText(/불러오는 중/)).toBeInTheDocument()
    resolve(resp())
    await waitFor(() => expect(screen.getByText('삼성바이오로직스')).toBeInTheDocument())
  })

  it('조회 실패 → 안내 + 다시 시도(무한 스피너 금지)', async () => {
    fetchScreener.mockRejectedValue(new Error('boom'))
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText(/후보 조회에 실패/)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: '다시 시도' })).toBeInTheDocument()
  })

  it('partial_failure → 안내 노트', async () => {
    fetchScreener.mockResolvedValue(resp({ partial_failure: ['999999'] }))
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText(/일부 종목/)).toBeInTheDocument())
  })

  it('면책 고지 상시 노출', async () => {
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText(/투자 책임은/)).toBeInTheDocument())
  })
})
