import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { authFetch, getToken, setToken, clearToken, login, signup, fetchMe, logout } from './auth.js'

// Node 22 의 실험적 전역 localStorage 는 clear 가 없어 flaky → 인메모리 스텁으로 대체(테스트 전용).
beforeEach(() => {
  const store = {}
  vi.stubGlobal('localStorage', {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => {
      store[k] = String(v)
    },
    removeItem: (k) => {
      delete store[k]
    },
    clear: () => {
      for (const k of Object.keys(store)) delete store[k]
    },
  })
})
afterEach(() => vi.unstubAllGlobals())

describe('토큰 저장', () => {
  it('set/get/clear', () => {
    expect(getToken()).toBeNull()
    setToken('abc')
    expect(getToken()).toBe('abc')
    clearToken()
    expect(getToken()).toBeNull()
  })
})

describe('authFetch', () => {
  it('토큰 있으면 Authorization: Bearer 주입', async () => {
    setToken('tok123')
    const fetchMock = vi.fn(async () => ({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)
    await authFetch('/api/watchlist')
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer tok123')
  })

  it('토큰 없으면 Authorization 미주입', async () => {
    const fetchMock = vi.fn(async () => ({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)
    await authFetch('/api/watchlist')
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBeUndefined()
  })
})

describe('login/signup', () => {
  it('login 성공 → 토큰 저장 + 반환', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true, json: async () => ({ token: 'T', user: { id: 1, email: 'a@b.com' } }),
    })))
    const data = await login('a@b.com', 'pw')
    expect(data.user.email).toBe('a@b.com')
    expect(getToken()).toBe('T')
  })

  it('login 실패 → err.status 실어 throw, 토큰 미저장', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false, status: 401, json: async () => ({ detail: '불일치' }),
    })))
    await expect(login('a@b.com', 'bad')).rejects.toMatchObject({ status: 401 })
    expect(getToken()).toBeNull()
  })

  it('signup 성공 → 토큰 저장', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true, json: async () => ({ token: 'S', user: { id: 2, email: 'n@x.com' } }),
    })))
    await signup('n@x.com', 'password123')
    expect(getToken()).toBe('S')
  })
})

describe('fetchMe', () => {
  it('토큰 없으면 null(요청 안 함)', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    expect(await fetchMe()).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('토큰 있고 200 → user', async () => {
    setToken('T')
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ id: 1, email: 'a@b.com' }) })))
    expect(await fetchMe()).toEqual({ id: 1, email: 'a@b.com' })
  })

  it('토큰 무효(401) → null', async () => {
    setToken('bad')
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 401 })))
    expect(await fetchMe()).toBeNull()
  })
})

describe('logout', () => {
  it('토큰 제거', () => {
    setToken('T')
    logout()
    expect(getToken()).toBeNull()
  })
})
