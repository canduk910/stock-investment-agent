import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import SegmentedControl from './SegmentedControl.jsx'

const OPTS = [
  { key: 'a', label: 'A안' },
  { key: 'b', label: 'B안' },
]

// 계약: 버튼 배열만(래퍼 없음) · type=button · aria-pressed · 클릭 시 onChange(키) · 클래스 prop 주입.
describe('SegmentedControl', () => {
  it('옵션마다 버튼을 그리고 활성만 aria-pressed=true', () => {
    const { getByText } = render(
      <SegmentedControl options={OPTS} value="b" onChange={() => {}} buttonClass="seg" />,
    )
    expect(getByText('A안').getAttribute('aria-pressed')).toBe('false')
    expect(getByText('B안').getAttribute('aria-pressed')).toBe('true')
    expect(getByText('A안').getAttribute('type')).toBe('button')
    expect(getByText('A안').className).toBe('seg')
  })

  it('activeClass 지정 시 활성 버튼에만 추가(스크리너 is-active 패턴)', () => {
    const { getByText } = render(
      <SegmentedControl options={OPTS} value="a" onChange={() => {}} buttonClass="chip" activeClass="is-active" />,
    )
    expect(getByText('A안').className).toBe('chip is-active')
    expect(getByText('B안').className).toBe('chip')
  })

  it('클릭 시 onChange(키) 호출·disabled 면 미발화(차트 로딩 중 전환 방지)', () => {
    const onChange = vi.fn()
    const { getByText, rerender } = render(
      <SegmentedControl options={OPTS} value="a" onChange={onChange} buttonClass="seg" />,
    )
    fireEvent.click(getByText('B안'))
    expect(onChange).toHaveBeenCalledWith('b')
    rerender(
      <SegmentedControl options={OPTS} value="a" onChange={onChange} buttonClass="seg" disabled />,
    )
    fireEvent.click(getByText('B안'))
    expect(onChange).toHaveBeenCalledTimes(1) // disabled → 추가 발화 없음
  })

  it('keyOf 주입 — months 같은 비표준 키 필드도 지원(궤적 기간 탭)', () => {
    const onChange = vi.fn()
    const opts = [{ months: 12, label: '1년' }, { months: 24, label: '2년' }]
    const { getByText } = render(
      <SegmentedControl options={opts} value={24} onChange={onChange} buttonClass="r" keyOf={(o) => o.months} />,
    )
    expect(getByText('2년').getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(getByText('1년'))
    expect(onChange).toHaveBeenCalledWith(12)
  })
})
