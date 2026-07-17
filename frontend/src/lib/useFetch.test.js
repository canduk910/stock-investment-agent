import { describe, it, expect, vi } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { useFetch } from './useFetch.js'

describe('useFetch', () => {
  it('마운트 시 조회 → data 세팅·loading false', async () => {
    const apiCall = vi.fn().mockResolvedValue({ x: 1 })
    const { result } = renderHook(() => useFetch(apiCall))
    expect(result.current.loading).toBe(true) // 초기 true
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual({ x: 1 })
    expect(result.current.error).toBe(null)
    expect(apiCall).toHaveBeenCalledTimes(1)
  })

  it('실패 → error=message·loading false', async () => {
    const apiCall = vi.fn().mockRejectedValue(new Error('API 500'))
    const { result } = renderHook(() => useFetch(apiCall))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe('API 500')
  })

  it('onData 성공 콜백(부모 통지)', async () => {
    const onData = vi.fn()
    const { result } = renderHook(() => useFetch(vi.fn().mockResolvedValue('v'), [], onData))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(onData).toHaveBeenCalledWith('v')
  })

  it('reload → 재조회(error clear)', async () => {
    const apiCall = vi.fn().mockRejectedValueOnce(new Error('e')).mockResolvedValue('ok')
    const { result } = renderHook(() => useFetch(apiCall))
    await waitFor(() => expect(result.current.error).toBe('e'))
    await act(async () => {
      await result.current.reload()
    })
    expect(result.current.error).toBe(null)
    expect(result.current.data).toBe('ok')
  })
})
