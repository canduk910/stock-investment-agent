import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import GrandCyclePanel from './GrandCyclePanel.jsx'

// 고지로 이동평균선 대순환 카드 — 6단계 스텝(현재 강조)·밴드·지속·인사이트·면책. null → 보류 안내.
// 데이터(단계·밴드)는 백엔드 summary.ma_grand_cycle, 6단계 라벨은 indicator_config.grand_cycle(카탈로그).

const CATALOG = {
  periods: { short: 5, medium: 20, long: 40 },
  stages: [
    { stage: 1, name: '안정 상승기', arrangement: '단 > 중 > 장', phase: '상승' },
    { stage: 2, name: '상승 둔화기', arrangement: '중 > 단 > 장', phase: '상승' },
    { stage: 3, name: '하락 진입기', arrangement: '중 > 장 > 단', phase: '전환' },
    { stage: 4, name: '안정 하락기', arrangement: '장 > 중 > 단', phase: '하락' },
    { stage: 5, name: '하락 둔화기', arrangement: '장 > 단 > 중', phase: '하락' },
    { stage: 6, name: '상승 진입기', arrangement: '단 > 장 > 중', phase: '전환' },
  ],
}

const CYCLE = {
  stage: 1,
  stage_name: '안정 상승기',
  arrangement: '단 > 중 > 장',
  phase: '상승',
  ma: { short: 190, medium: 152.5, long: 126.25 },
  periods: { short: 5, medium: 20, long: 40 },
  band_width_pct: 3.24,
  band_direction: '확대',
  bars_in_stage: 12,
  prev_stage: null,
}

describe('GrandCyclePanel', () => {
  it('6단계 스텝 렌더 — 현재 단계만 강조(--current)', () => {
    const { container } = render(<GrandCyclePanel cycle={CYCLE} catalog={CATALOG} />)
    const steps = container.querySelectorAll('.grand-cycle__step')
    expect(steps).toHaveLength(6)
    const current = container.querySelectorAll('.grand-cycle__step--current')
    expect(current).toHaveLength(1)
    expect(current[0].textContent).toContain('안정 상승기')
  })

  it('현재 단계 배지·밴드·지속 readout 표시', () => {
    const { container } = render(<GrandCyclePanel cycle={CYCLE} catalog={CATALOG} />)
    expect(screen.getByText('1단계')).toBeInTheDocument()
    expect(container.textContent).toContain('+3.24% · 확대') // 밴드
    expect(container.textContent).toContain('12봉') // 지속
  })

  it('핵심 인사이트 서술 + 면책 고정 노출', () => {
    const { container } = render(<GrandCyclePanel cycle={CYCLE} catalog={CATALOG} />)
    expect(container.querySelector('.grand-cycle__insight').textContent).toContain('안정 상승기')
    // 면책(매매 권유 아님)이 항상 보인다.
    expect(container.querySelector('.grand-cycle__disclaimer')).toBeTruthy()
    expect(container.textContent).toMatch(/권유하지 않|투자 판단/)
  })

  it('cycle null → 스텝 없이 보류 안내(muted graceful)', () => {
    const { container } = render(<GrandCyclePanel cycle={null} catalog={CATALOG} />)
    expect(container.querySelector('.grand-cycle__empty')).toBeTruthy()
    expect(container.querySelectorAll('.grand-cycle__step')).toHaveLength(0)
  })

  it('카탈로그 없어도 현재 단계 배지는 cycle 로 표시(graceful)', () => {
    const { container } = render(<GrandCyclePanel cycle={CYCLE} catalog={null} />)
    expect(screen.getByText('1단계')).toBeInTheDocument()
    // 6-스텝 라벨은 카탈로그가 없으면 생략(프론트가 6단계 이름을 복제하지 않음).
    expect(container.querySelectorAll('.grand-cycle__step')).toHaveLength(0)
  })
})
