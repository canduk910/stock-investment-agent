import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import LoadState from './LoadState.jsx'

// 계약: popup__state 박스 · 로딩 우선 · 에러(+옵션 재시도) · 둘 다 아니면 children.
describe('LoadState', () => {
  it('loading — popup__state 박스에 로딩 문구', () => {
    const { container } = render(<LoadState loading loadingText="불러오는 중…" />)
    expect(container.querySelector('.popup__state').textContent).toBe('불러오는 중…')
  })

  it('error — errorContent 그대로 + onRetry 있으면 재시도 버튼(라벨·클래스 주입)', () => {
    const onRetry = vi.fn()
    const { container, getByText } = render(
      <LoadState
        error
        errorContent={<span>조회 실패: 원인</span>}
        onRetry={onRetry}
        retryLabel="다시 시도"
        retryClassName="refresh admin__retry"
      />,
    )
    expect(container.querySelector('.popup__state span').textContent).toBe('조회 실패: 원인')
    const btn = getByText('다시 시도')
    expect(btn.className).toBe('refresh admin__retry')
    fireEvent.click(btn)
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('error — onRetry 없으면 버튼 생략(재시도 없는 오버레이 자리)', () => {
    const { container } = render(<LoadState error errorContent="실패" />)
    expect(container.querySelector('button')).toBeNull()
  })

  it('평상시 — children 을 그대로 반환(래퍼형)', () => {
    const { getByText } = render(
      <LoadState loading={false} error={null}>
        <div>본문</div>
      </LoadState>,
    )
    expect(getByText('본문')).toBeTruthy()
  })
})
