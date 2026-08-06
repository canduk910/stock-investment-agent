import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import ScreenerPanel from './ScreenerPanel.jsx'

// 경계(api.js)만 mock. 강화된 스크리너 카드 계약 검증:
//   - 백엔드가 시총 역순 정렬 + stage 필터 + 표시 top-N enrich 를 마쳤으므로 프론트는 응답 순서대로
//     렌더한다(클라이언트 재정렬 없음).
//   - 카드는 가격 + 등락 칩 + 미니 스파크라인 + PER + 재무 100점 점수(게이지)를 표시.
//   - stage 필터는 서버 파라미터 — 선택 시 재조회(fetchScreener 에 stage 전달).
//   - score_config(max_score) 소비. price/per/fin_score null 은 "—" graceful.

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

const SCORE_CONFIG = {
  max_score: 100,
  axis_max: 25,
  axes: [
    { key: 'profitability', axis: '수익성', label: '수익성(ROE)', unit: '%', direction: 'high', max: 25 },
    { key: 'growth', axis: '성장성', label: '성장성(순이익)', unit: '%', direction: 'high', max: 25 },
    { key: 'stability', axis: '안정성', label: '안정성(부채비율)', unit: '%', direction: 'low', max: 25 },
    { key: 'valuation', axis: '밸류에이션', label: '밸류(PER)', unit: '배', direction: 'low', max: 25 },
  ],
}

// 전체 보통주 스캔 결과(DB) — 표시 top-N 은 라이브 시세/재무점수 enrich 완료(시총 역순 정렬).
function resp(overrides = {}) {
  return {
    candidates: [
      // 시총 역순으로 백엔드가 이미 정렬(삼성전자 > SK하이닉스 > 삼성바이오)
      {
        ticker: '005930', name: '삼성전자', market: 'KOSPI',
        stage: 1, stage_name: '안정 상승기', arrangement: '단 > 중 > 장',
        band_width_pct: 2.6, band_direction: '확대', bars_in_stage: 5,
        market_cap: 4500000, spark: [100, 102, 105, 104, 108],
        price: 70000, change_rate: 1.24, per: 15.3, per_vs_avg: -5.0,
        fin_score: 72,
        fin_axes: [
          { key: 'profitability', axis: '수익성', label: '수익성(ROE)', value: 12.5, points: 20, max: 25 },
          { key: 'growth', axis: '성장성', label: '성장성(순이익)', value: 8.0, points: 18, max: 25 },
          { key: 'stability', axis: '안정성', label: '안정성(부채비율)', value: 40.0, points: 20, max: 25 },
          { key: 'valuation', axis: '밸류에이션', label: '밸류(PER)', value: 15.3, points: 14, max: 25 },
        ],
        roe: 12.5, net_income_growth: 8.0, debt_ratio: 40.0, avg_per: 16.1,
      },
      {
        ticker: '000660', name: 'SK하이닉스', market: 'KOSPI',
        stage: 6, stage_name: '상승 진입기', arrangement: '단 > 장 > 중',
        band_width_pct: 1.2, band_direction: '확대', bars_in_stage: 2,
        market_cap: 1300000, spark: [50, 49, 48, 47],
        price: 130000, change_rate: -0.8, per: 9.1, per_vs_avg: 3.0,
        fin_score: 55, fin_axes: [], roe: null, net_income_growth: null, debt_ratio: null, avg_per: null,
      },
      {
        // enrich 실패(라이브 시세/재무점수 없음) — graceful "—". 단계는 4(배지 중복 회피용 구분).
        ticker: '207940', name: '삼성바이오로직스', market: 'KOSPI',
        stage: 4, stage_name: '안정 하락기', arrangement: '장 > 중 > 단',
        band_width_pct: -3.4, band_direction: '축소', bars_in_stage: 8,
        market_cap: 700000, spark: null,
        price: null, change_rate: null, per: null, per_vs_avg: null,
        fin_score: null, fin_axes: [], roe: null, net_income_growth: null, debt_ratio: null, avg_per: null,
      },
    ],
    catalog: CATALOG,
    score_config: SCORE_CONFIG,
    market: 'all',
    market_iscd: '0000',
    scope: 'cached',
    as_of: '2026-08-03',
    stage: 'rising',
    total: 3,
    displayed: 3,
    universe_size: 2000,
    partial_failure: [],
    ...overrides,
  }
}

beforeEach(() => {
  fetchScreener.mockReset().mockResolvedValue(resp())
})

describe('ScreenerPanel (강화 카드 — 가격·스파크·PER·재무점수)', () => {
  it('cached 헤더(스캔일·유니버스) + 종목명·단계 배지', async () => {
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText('삼성전자')).toBeInTheDocument())
    expect(screen.getByText(/2026-08-03/)).toBeInTheDocument()
    expect(screen.getByText(/2,000종목/)).toBeInTheDocument()
    expect(screen.getByText('SK하이닉스')).toBeInTheDocument()
    // 단계 배지(종목명 + 단계) — catalog 라벨 SSOT
    expect(screen.getByText(/1단계 · 안정 상승기/)).toBeInTheDocument()
    expect(screen.getByText(/6단계 · 상승 진입기/)).toBeInTheDocument()
  })

  it('백엔드 시총 역순 정렬을 그대로 렌더(클라이언트 재정렬 없음)', async () => {
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText('삼성전자')).toBeInTheDocument())
    // DOM 순서 = 응답 순서(삼성전자 → SK하이닉스 → 삼성바이오)
    const names = screen.getAllByText(/삼성전자|SK하이닉스|삼성바이오로직스/).map((n) => n.textContent)
    expect(names).toEqual(['삼성전자', 'SK하이닉스', '삼성바이오로직스'])
  })

  it('카드에 가격 + 등락 칩 + PER 표시', async () => {
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText('삼성전자')).toBeInTheDocument())
    // 가격(라이브 enrich)
    expect(screen.getByText('70,000원')).toBeInTheDocument()
    expect(screen.getByText('130,000원')).toBeInTheDocument()
    // 등락 칩(방향색 클래스는 ChangeChip SSOT — 여기선 값·부호만). signedNum 기본 2자리(-0.80%).
    expect(screen.getByText(/\+1\.24%/)).toBeInTheDocument()
    expect(screen.getByText(/-0\.80%/)).toBeInTheDocument()
    // PER
    expect(screen.getByText('PER 15.3')).toBeInTheDocument()
    expect(screen.getByText('PER 9.1')).toBeInTheDocument()
  })

  it('미니 스파크라인(spark 있는 종목만 렌더·null 은 생략)', async () => {
    const { container } = render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText('삼성전자')).toBeInTheDocument())
    // 삼성전자·SK하이닉스는 spark 있음(2개), 삼성바이오는 null → 생략
    expect(container.querySelectorAll('.wl__spark').length).toBe(2)
  })

  it('PER 오른편 재무 100점 점수 + 게이지(색은 방향색 아님)', async () => {
    const { container } = render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText('삼성전자')).toBeInTheDocument())
    // 재무점수 숫자(score_config.max_score=100 을 분모로)
    expect(screen.getByText('72/100')).toBeInTheDocument()
    expect(screen.getByText('55/100')).toBeInTheDocument()
    // 게이지 채움 폭 = 점수%(72 → 72%). 방향색(up/down) 클래스가 아니어야 한다.
    const fills = container.querySelectorAll('.screener__score-fill')
    expect(fills.length).toBeGreaterThanOrEqual(2)
    expect(fills[0].getAttribute('style')).toMatch(/width:\s*72%/)
    expect(fills[0].className).not.toMatch(/\bup\b|\bdown\b/)
  })

  it('score_config.max_score 를 분모로 소비(커스텀 max)', async () => {
    fetchScreener.mockResolvedValue(
      resp({ score_config: { ...SCORE_CONFIG, max_score: 120 } }),
    )
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText('삼성전자')).toBeInTheDocument())
    expect(screen.getByText('72/120')).toBeInTheDocument()
  })

  it('null graceful — 가격·PER·재무점수 미enrich 종목은 "—"', async () => {
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText('삼성바이오로직스')).toBeInTheDocument())
    // 삼성바이오 카드 안에서 가격/PER/점수가 "—"
    const bio = screen.getByText('삼성바이오로직스').closest('.wl__row')
    expect(within(bio).getByText('PER —')).toBeInTheDocument()
    expect(within(bio).getByText('—/100')).toBeInTheDocument()
  })

  it("stage 필터는 서버 파라미터 — 선택 시 stage 로 재조회", async () => {
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText('삼성전자')).toBeInTheDocument())
    // 초기: 기본 상승국면(rising)
    expect(fetchScreener).toHaveBeenCalledWith('all', 'rising')
    // '4단계' 클릭 → 서버 stage='4' 로 재조회(클라이언트 필터 아님)
    fireEvent.click(screen.getByRole('button', { name: '4단계' }))
    await waitFor(() => expect(fetchScreener).toHaveBeenCalledWith('all', '4'))
    // '전체 단계' → stage='all'
    fireEvent.click(screen.getByRole('button', { name: '전체 단계' }))
    await waitFor(() => expect(fetchScreener).toHaveBeenCalledWith('all', 'all'))
  })

  it('시장 선택기 → 해당 market·stage 로 재조회(scope 는 api 내부 cached 고정)', async () => {
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText('삼성전자')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: '코스닥' }))
    await waitFor(() => expect(fetchScreener).toHaveBeenCalledWith('kosdaq', 'rising'))
  })

  it('시장 선택기에 kospi200 없음(cached 미지원)', async () => {
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText('삼성전자')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: '전체' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '코스피' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '코스닥' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '코스피200' })).not.toBeInTheDocument()
  })

  it('scope=live 폴백 → 전체 스캔 전 임시 표시 안내(fin_score 없어도 graceful)', async () => {
    fetchScreener.mockResolvedValue(
      resp({
        scope: 'live',
        universe_size: 30,
        as_of: null,
        candidates: [
          {
            ticker: '005930', name: '삼성전자', market: 'KOSPI',
            stage: 1, stage_name: '안정 상승기', arrangement: '단 > 중 > 장',
            band_width_pct: 2.6, band_direction: '확대', bars_in_stage: 5,
            market_cap: 4500000, spark: [1, 2, 3], price: 70000, change_rate: 1.2,
            per: 15.3, fin_score: null, fin_axes: [],
          },
        ],
      }),
    )
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText('삼성전자')).toBeInTheDocument())
    expect(screen.getByText(/전체 스캔 전/)).toBeInTheDocument()
    // 라이브 폴백은 fin_score 없을 수 있음 → "—/100"
    expect(screen.getByText('—/100')).toBeInTheDocument()
  })

  it('"외 N종목" = total - displayed(음수 방지)', async () => {
    fetchScreener.mockResolvedValue(resp({ total: 250, displayed: 3 }))
    render(<ScreenerPanel />)
    await waitFor(() => expect(screen.getByText('삼성전자')).toBeInTheDocument())
    expect(screen.getByText(/외 247종목/)).toBeInTheDocument()
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
    await waitFor(() => expect(screen.getByText('삼성전자')).toBeInTheDocument())
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
