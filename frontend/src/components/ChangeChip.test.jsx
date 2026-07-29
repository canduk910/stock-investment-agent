import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import ChangeChip from './ChangeChip.jsx'

// 등락 칩 계약: 방향 클래스 + ▲▼─ 글리프(aria-hidden) + 부호 있는 % — 기존 3곳 인라인과 동일 출력.
describe('ChangeChip', () => {
  it('상승: up 클래스·▲·+부호', () => {
    const { container } = render(<ChangeChip value={3.2} />)
    const chip = container.querySelector('.wl__change')
    expect(chip.className).toContain('up')
    expect(chip.textContent).toContain('▲')
    expect(chip.textContent).toContain('+3.20%')
  })

  it('하락: down 클래스·▼·-부호', () => {
    const { container } = render(<ChangeChip value={-1.5} />)
    const chip = container.querySelector('.wl__change')
    expect(chip.className).toContain('down')
    expect(chip.textContent).toContain('▼')
    expect(chip.textContent).toContain('-1.50%')
  })

  it('결측: 방향 클래스 없음(회색)·─·— 표기, 글리프는 aria-hidden', () => {
    const { container } = render(<ChangeChip value={null} />)
    const chip = container.querySelector('.wl__change')
    expect(chip.className).not.toContain('up')
    expect(chip.className).not.toContain('down')
    expect(chip.textContent).toContain('─')
    expect(chip.textContent).toContain('—%')
    expect(chip.querySelector('[aria-hidden="true"]')).toBeTruthy()
  })

  it('className 주입 — 리포트 자리(report__change)에서도 같은 구조', () => {
    const { container } = render(<ChangeChip value={0} className="report__change" />)
    const chip = container.querySelector('.report__change')
    expect(chip.textContent).toContain('─') // 보합 글리프
    expect(chip.className).toContain('flat') // changeDir(0)='flat'
  })
})
