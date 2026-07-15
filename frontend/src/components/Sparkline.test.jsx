import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import Sparkline from './Sparkline.jsx'

// 공용 스파크라인 — 관심종목·잔고 공유. 선색=방향색 토큰(theme.css), points<2/결측이면 렌더 생략.
// dir 명시 시 그 방향(null=회색), 미지정 시 스파크 추세(마지막 vs 첫)로 자동 도출.

const stroke = (container) => container.querySelector('path')?.getAttribute('stroke')

describe('Sparkline(공용 미니차트)', () => {
  it('2점 이상이면 SVG path 렌더', () => {
    const { container } = render(<Sparkline points={[100, 110, 105]} />)
    expect(container.querySelector('svg')).toBeTruthy()
    expect(container.querySelector('path')).toBeTruthy()
  })

  it('2점 미만·비배열·전량 비수치 → 렌더 안 함(null)', () => {
    expect(render(<Sparkline points={[100]} />).container.querySelector('svg')).toBeFalsy()
    expect(render(<Sparkline points={null} />).container.querySelector('svg')).toBeFalsy()
    // 유효 수치 2개 미만(비수치는 필터됨) → 생략.
    expect(render(<Sparkline points={[undefined, undefined]} />).container.querySelector('svg')).toBeFalsy()
  })

  it('dir 미지정 → 스파크 추세로 자동 색(상승=--c-up, 하락=--c-down)', () => {
    expect(stroke(render(<Sparkline points={[100, 120]} />).container)).toBe('var(--c-up)')
    expect(stroke(render(<Sparkline points={[120, 100]} />).container)).toBe('var(--c-down)')
    // 첫=끝(보합) → 회색.
    expect(stroke(render(<Sparkline points={[100, 130, 100]} />).container)).toBe('var(--c-flat)')
  })

  it('dir 명시 → 그 방향색 사용(추세 무관), null 이면 회색(기존 관심종목 동작 보존)', () => {
    // 상승 추세지만 dir="down" 명시 → 파랑.
    expect(stroke(render(<Sparkline points={[100, 120]} dir="down" />).container)).toBe('var(--c-down)')
    // dir={null} → 회색(관심종목이 change_rate 결측 시 넘기는 값).
    expect(stroke(render(<Sparkline points={[100, 120]} dir={null} />).container)).toBe('var(--c-flat)')
  })

  it('className prop 으로 클래스 지정(기본 wl__spark)', () => {
    expect(render(<Sparkline points={[1, 2]} />).container.querySelector('.wl__spark')).toBeTruthy()
  })
})
