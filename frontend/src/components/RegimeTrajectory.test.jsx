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
  it('매트릭스 트레일 렌더 — 점 N개·연결선·현재 주황 점·현재 라벨', async () => {
    const { container } = render(<RegimeTrajectory />)
    await waitFor(() => expect(container.querySelector('svg.rtraj__svg')).toBeTruthy())
    expect(container.querySelectorAll('circle.rtraj__dot')).toHaveLength(3)
    expect(container.querySelector('circle.rtraj__dot--current')).toBeTruthy()
    expect(container.querySelector('path.rtraj__trail')).toBeTruthy()
    // 현재 지점 라벨(월·국면).
    expect(screen.getByText(/2024\.03 · 수축/)).toBeInTheDocument()
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
})
