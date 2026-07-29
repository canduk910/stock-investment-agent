import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { useModalOverlay } from './useModalOverlay.js'

// 훅 계약: 닫기버튼 포커스 · Esc → onClose · body 스크롤 잠금/복원.
function Overlay({ onClose }) {
  const closeRef = useModalOverlay(onClose)
  return (
    <div role="dialog">
      <button ref={closeRef} onClick={onClose} aria-label="닫기">✕</button>
    </div>
  )
}

describe('useModalOverlay', () => {
  it('마운트 시 닫기 버튼에 포커스한다(접근성)', () => {
    const { getByLabelText } = render(<Overlay onClose={() => {}} />)
    expect(document.activeElement).toBe(getByLabelText('닫기'))
  })

  it('Escape 키로 onClose 를 호출한다', () => {
    const onClose = vi.fn()
    render(<Overlay onClose={onClose} />)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
    fireEvent.keyDown(document, { key: 'Enter' }) // 다른 키는 무시
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('body 스크롤을 잠그고 언마운트 시 이전 값을 복원한다', () => {
    document.body.style.overflow = 'auto'
    const { unmount } = render(<Overlay onClose={() => {}} />)
    expect(document.body.style.overflow).toBe('hidden')
    unmount()
    expect(document.body.style.overflow).toBe('auto')
  })
})
