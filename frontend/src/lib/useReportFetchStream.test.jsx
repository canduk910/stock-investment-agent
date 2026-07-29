import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { useReportFetchStream, formatFetchResult } from './useReportFetchStream.js'

// 훅 계약: [진행 시작 → done 안내 → 진행 종료 → after 재조회 → fetching 해제] + 끊김 폴백.
function Harness({ streamFn, fallbackFn, after }) {
  const { fetching, fetchMsg, progress, run } = useReportFetchStream()
  return (
    <div>
      <button onClick={() => run(streamFn, fallbackFn, after)}>go</button>
      <span data-testid="fetching">{String(fetching)}</span>
      <span data-testid="msg">{fetchMsg ?? ''}</span>
      <span data-testid="progress">{progress ? progress.stage : 'none'}</span>
    </div>
  )
}

describe('formatFetchResult', () => {
  it('완료 안내문 SSOT — 실패 0건이면 실패 문구 생략', () => {
    expect(formatFetchResult({ new: 2, fetched: 5, failed: 0 })).toBe('새 요약 2건 · 확인 5건')
    expect(formatFetchResult({ new: 1, fetched: 3, failed: 2 })).toBe(
      '새 요약 1건 · 확인 3건 · 실패 2건',
    )
  })
})

describe('useReportFetchStream', () => {
  it('done 이벤트 → 완료 안내 + after 재조회 + fetching 해제', async () => {
    const after = vi.fn().mockResolvedValue(['r1'])
    const streamFn = vi.fn(async ({ onEvent }) => {
      onEvent({ type: 'stage', stage: 'list' })
      onEvent({ type: 'done', new: 1, fetched: 4, failed: 0 })
    })
    render(<Harness streamFn={streamFn} fallbackFn={vi.fn()} after={after} />)
    fireEvent.click(screen.getByText('go'))
    await waitFor(() => expect(screen.getByTestId('fetching').textContent).toBe('false'))
    expect(screen.getByTestId('msg').textContent).toBe('새 요약 1건 · 확인 4건')
    expect(screen.getByTestId('progress').textContent).toBe('none') // 진행바 종료
    expect(after).toHaveBeenCalledTimes(1)
  })

  it('done 없이 끊기면(onError) 논스트림 폴백 결과로 안내한다', async () => {
    const streamFn = vi.fn(async ({ onError }) => {
      await onError(new Error('stream cut'))
    })
    const fallbackFn = vi.fn().mockResolvedValue({ new: 0, fetched: 2, failed: 1 })
    render(<Harness streamFn={streamFn} fallbackFn={fallbackFn} after={undefined} />)
    fireEvent.click(screen.getByText('go'))
    await waitFor(() =>
      expect(screen.getByTestId('msg').textContent).toBe('새 요약 0건 · 확인 2건 · 실패 1건'),
    )
    expect(fallbackFn).toHaveBeenCalledTimes(1)
  })

  it('done 수신 후의 onError 는 무시한다(finished 가드 — 안내문 유지)', async () => {
    const fallbackFn = vi.fn()
    const streamFn = vi.fn(async ({ onEvent, onError }) => {
      onEvent({ type: 'done', new: 3, fetched: 3, failed: 0 })
      await onError(new Error('late error'))
    })
    render(<Harness streamFn={streamFn} fallbackFn={fallbackFn} />)
    fireEvent.click(screen.getByText('go'))
    await waitFor(() => expect(screen.getByTestId('msg').textContent).toBe('새 요약 3건 · 확인 3건'))
    expect(fallbackFn).not.toHaveBeenCalled() // 폴백 미발화
  })
})
