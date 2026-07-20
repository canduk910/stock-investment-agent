import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import RegimeTrajectory from './RegimeTrajectory.jsx'

// 국면 궤적 — 경계(api.js)만 mock. 매트릭스 트레일 렌더·기간 탭 재조회·graceful 상태·면책 검증.

vi.mock('../api.js', () => ({ fetchRegimeTrajectory: vi.fn() }))
import { fetchRegimeTrajectory } from '../api.js'

const DATA = {
  months: 36,
  interval: 'monthly',
  available: true,
  partial_failure: [],
  points: [
    { date: '2024-01-01', cycle_score: 2, sentiment_score: 2, regime: '확장', recommended_cash_ratio: 60 },
    { date: '2024-02-01', cycle_score: 0, sentiment_score: 1, regime: '과열', recommended_cash_ratio: 80 },
    { date: '2024-03-01', cycle_score: -2, sentiment_score: -2, regime: '수축', recommended_cash_ratio: 20 },
  ],
}

beforeEach(() => {
  fetchRegimeTrajectory.mockReset().mockResolvedValue(DATA)
})

describe('RegimeTrajectory', () => {
  it('매트릭스 트레일 렌더 — 정차점 N개(균일)·연결선·현재 주황·정차점 월 라벨', async () => {
    const { container } = render(<RegimeTrajectory />)
    await waitFor(() => expect(container.querySelector('svg.rtraj__svg')).toBeTruthy())
    const dots = container.querySelectorAll('circle.rtraj__dot')
    expect(dots).toHaveLength(3)
    // 크기 균일 — 모든 정차점 반지름이 동일(크기로 구분하지 않음).
    const radii = [...dots].map((d) => d.getAttribute('r'))
    expect(new Set(radii).size).toBe(1)
    expect(container.querySelector('circle.rtraj__dot--current')).toBeTruthy()
    expect(container.querySelector('path.rtraj__trail')).toBeTruthy()
    // 각 과거 정차점에 시작월 라벨(현재는 별도 강조 라벨).
    const stopLabels = [...container.querySelectorAll('text.rtraj__stoplabel')].map((t) => t.textContent)
    expect(stopLabels).toEqual(['24.01', '24.02'])
    // 현재 지점 강조 라벨(월·국면).
    expect(screen.getByText(/24\.03 · 수축/)).toBeInTheDocument()
    // 면책 상시.
    expect(screen.getByText(/미래 예측이 아닙니다/)).toBeInTheDocument()
  })

  it('방향 화살표는 끝점 하나만(과밀 제거) — 전환마다 붙던 seg 라인 없음', async () => {
    const { container } = render(<RegimeTrajectory />)
    await waitFor(() => expect(container.querySelector('path.rtraj__trail')).toBeTruthy())
    // 방향은 경로 끝점 화살표 하나(marker-end)로만 표시.
    expect(container.querySelector('path.rtraj__trail').getAttribute('marker-end')).toContain(
      'rtraj-arrow',
    )
    // 전환 세그먼트마다 붙던 화살표 라인은 제거됐다.
    expect(container.querySelectorAll('line.rtraj__seg')).toHaveLength(0)
  })

  it('기간 탭(1년) 클릭 → months=12 로 재조회(기본은 2년)', async () => {
    render(<RegimeTrajectory />)
    await waitFor(() => expect(fetchRegimeTrajectory).toHaveBeenCalledWith(24)) // 기본 2년(단순화)
    fireEvent.click(screen.getByRole('button', { name: '1년' }))
    await waitFor(() => expect(fetchRegimeTrajectory).toHaveBeenCalledWith(12))
  })

  it('available:false → 안내(무한 스피너 아님)', async () => {
    fetchRegimeTrajectory.mockResolvedValue({
      months: 36, interval: 'monthly', available: false, partial_failure: [], points: [],
      note: '국면 궤적을 불러오지 못했습니다(지표 히스토리 조회 실패).',
    })
    render(<RegimeTrajectory />)
    await waitFor(() => expect(screen.getByText(/지표 히스토리 조회 실패/)).toBeInTheDocument())
  })

  it('공포탐욕 결측이면 VIX 판정 안내(궤적은 유지)', async () => {
    fetchRegimeTrajectory.mockResolvedValue({ ...DATA, partial_failure: ['fear_greed'] })
    const { container } = render(<RegimeTrajectory />)
    await waitFor(() => expect(container.querySelector('svg.rtraj__svg')).toBeTruthy())
    expect(screen.getByText(/심리축은 VIX 로 판정/)).toBeInTheDocument()
  })

  it('조회 실패(HTTP/네트워크) → 재시도 버튼', async () => {
    fetchRegimeTrajectory.mockRejectedValue(new Error('API 500'))
    render(<RegimeTrajectory />)
    await waitFor(() => expect(screen.getByText(/불러오지 못했습니다/)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /재시도/ })).toBeInTheDocument()
  })

  it('live prop → 활성 셀 음영·라이브 마커+콜아웃·경기심리 readout, 마지막 정차점은 현재 아님', async () => {
    const live = { cs: 2, ss: 0, regime: '확장', cash: 60, confidence: 'high', cycleSign: '양호', sentimentSign: '중립' }
    const { container } = render(<RegimeTrajectory live={live} />)
    await waitFor(() => expect(container.querySelector('svg.rtraj__svg')).toBeTruthy())
    expect(container.querySelector('circle.rtraj__live-dot')).toBeTruthy() // 라이브 주황 마커
    expect(container.querySelector('rect.rtraj__cellfill')).toBeTruthy() // 활성 셀 음영
    expect(screen.getByText(/현재 · 확장/)).toBeInTheDocument() // 콜아웃
    expect(screen.getByText(/경기:/)).toBeInTheDocument() // 경기/심리 readout
    // 라이브가 있으면 마지막 정차점을 '현재'로 강조하지 않는다(강조는 라이브 마커 하나).
    expect(container.querySelector('circle.rtraj__dot--current')).toBeNull()
  })

  it('재방문 좌표의 월 라벨은 한 라벨로 병합(", " 조인)', async () => {
    fetchRegimeTrajectory.mockResolvedValue({
      months: 24, interval: 'monthly', available: true, partial_failure: [],
      points: [
        { date: '2024-01-01', cycle_score: 2, sentiment_score: 2, regime: '확장' },
        { date: '2024-02-01', cycle_score: -2, sentiment_score: -2, regime: '수축' },
        { date: '2024-03-01', cycle_score: 2, sentiment_score: 2, regime: '확장' }, // 확장 재방문
      ],
    })
    // live 주입 → 모든 정차점이 그룹 라벨 대상(레거시 현재 제외 없음).
    const live = { cs: 0, ss: 0, regime: '확장', cash: 60, confidence: 'high', cycleSign: '중립', sentimentSign: '중립' }
    const { container } = render(<RegimeTrajectory live={live} />)
    await waitFor(() => expect(container.querySelector('svg.rtraj__svg')).toBeTruthy())
    const labels = [...container.querySelectorAll('text.rtraj__stoplabel')].map((t) => t.textContent)
    expect(labels).toContain('24.01, 24.03') // 확장 재방문 두 월이 한 라벨로
    expect(labels).toContain('24.02') // 수축은 단일
  })

  it('년도별 밝기 그라데이션 — 과거 연도 라벨 옅게(--y0)·최근 연도 짙게(--y3) 클래스', async () => {
    fetchRegimeTrajectory.mockResolvedValue({
      months: 36, interval: 'monthly', available: true, partial_failure: [],
      points: [
        { date: '2024-05-01', cycle_score: 2, sentiment_score: 2, regime: '확장' },
        { date: '2025-06-01', cycle_score: -2, sentiment_score: -2, regime: '수축' },
        { date: '2026-01-01', cycle_score: 2, sentiment_score: 0, regime: '확장' },
      ],
    })
    // live 중앙(0,0) — 세 정차점과 좌표 달라 모두 라벨 대상.
    const live = { cs: 0, ss: 0, regime: '확장', cash: 60, confidence: 'high', cycleSign: '중립', sentimentSign: '중립' }
    const { container } = render(<RegimeTrajectory live={live} />)
    await waitFor(() => expect(container.querySelector('svg.rtraj__svg')).toBeTruthy())
    const labels = [...container.querySelectorAll('text.rtraj__stoplabel')]
    // 모든 라벨에 년도 밝기 레벨 클래스가 붙는다(색이 최근성을 전달).
    expect(labels.every((t) => /rtraj__stoplabel--y[0-3]/.test(t.getAttribute('class')))).toBe(true)
    // 가장 과거 연도(2024) = 옅게(y0), 가장 최근 연도(2026) = 짙게(y3).
    const y2024 = labels.find((t) => t.textContent.includes('24.'))
    const y2026 = labels.find((t) => t.textContent.includes('26.'))
    expect(y2024.getAttribute('class')).toContain('--y0')
    expect(y2026.getAttribute('class')).toContain('--y3')
  })

  it('범례에 표본 간격 라벨 표시(interval → 분기별/반기별/연별) — 기준 명시', async () => {
    fetchRegimeTrajectory.mockResolvedValue({
      months: 12, interval: 'quarterly', step_months: 3, available: true, partial_failure: [],
      points: [
        { date: '2024-03-01', cycle_score: 2, sentiment_score: 2, regime: '확장' },
        { date: '2024-06-01', cycle_score: -2, sentiment_score: -2, regime: '수축' },
        { date: '2024-09-01', cycle_score: 2, sentiment_score: 0, regime: '확장' },
      ],
    })
    render(<RegimeTrajectory />)
    await waitFor(() => expect(screen.getByText(/분기별/)).toBeInTheDocument())
  })

  it('라이브 셀 == 마지막 확정월 셀(안정 국면)이면 그 월 라벨을 억제(콜아웃과 겹침 방지)', async () => {
    fetchRegimeTrajectory.mockResolvedValue({
      months: 24, interval: 'monthly', available: true, partial_failure: [],
      points: [
        { date: '2024-05-01', cycle_score: -2, sentiment_score: -2, regime: '수축' },
        { date: '2024-06-01', cycle_score: 2, sentiment_score: 0, regime: '확장' }, // 마지막 확정월 = 확장 셀
      ],
    })
    // 라이브도 확장 셀(2,0) — 마지막 정차점과 동일 좌표(브릿지 없음·라벨 겹칠 자리).
    const live = { cs: 2, ss: 0, regime: '확장', cash: 60, confidence: 'high', cycleSign: '양호', sentimentSign: '중립' }
    const { container } = render(<RegimeTrajectory live={live} />)
    await waitFor(() => expect(container.querySelector('circle.rtraj__live-dot')).toBeTruthy())
    const labels = [...container.querySelectorAll('text.rtraj__stoplabel')].map((t) => t.textContent)
    expect(labels).not.toContain('24.06') // 라이브 셀의 확정월 라벨 억제(콜아웃이 담당)
    expect(labels).toContain('24.05') // 다른 셀(수축)은 유지
    expect(screen.getByText(/현재 · 확장/)).toBeInTheDocument() // 콜아웃은 표시
  })

  it('라이브 없어도 마지막 정차점을 현재로 강조하면 범례에 "현재" 표기(불일치 회귀 잠금)', async () => {
    const { container } = render(<RegimeTrajectory />)
    await waitFor(() => expect(container.querySelector('circle.rtraj__dot--current')).toBeTruthy())
    expect(container.querySelector('.rtraj__legend')?.textContent).toContain('현재')
  })
})
