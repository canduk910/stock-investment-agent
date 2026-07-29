// api.js characterization 테스트 — 리팩토링 안전망(M7 선행 조건).
// 지금까지 컴포넌트 테스트가 api.js 를 통째로 mock-out 해 이 파일 자체는 안전망이 0이었다.
// 여기서 44개 함수의 **관측 가능한 동작**(URL·메서드·헤더·바디·성공 반환·에러 shape)을
// "있는 그대로" 고정한다 — 내부 구조(헬퍼화)를 바꿔도 이 계약은 불변이어야 한다.
import { describe, it, expect, vi, beforeEach } from 'vitest'

// authFetch(Bearer 주입)·SSE 리더는 경계 mock — 여기선 "무엇으로 호출했는가"만 검증.
vi.mock('./auth.js', () => ({ authFetch: vi.fn() }))
vi.mock('./lib/sseChat.js', () => ({ readChatStream: vi.fn() }))
vi.mock('./lib/sse.js', () => ({ readSSE: vi.fn() }))

import { authFetch } from './auth.js'
import { readChatStream } from './lib/sseChat.js'
import { readSSE } from './lib/sse.js'
import * as api from './api.js'

// 가짜 Response — ok/status/json 만 흉내(fetch 표준 최소면).
function res(json = {}, { ok = true, status = 200 } = {}) {
  return { ok, status, json: async () => json }
}
// json() 이 실패하는 Response(빈 바디 등) — .catch(()=>({})) 경로 검증용.
function resBadJson({ ok = false, status = 500 } = {}) {
  return { ok, status, json: async () => { throw new Error('no body') } }
}

const gfetch = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('fetch', gfetch)
})

// ── 패턴 A: 공개 GET(fetch) — 실패는 `API {status}` Error ─────────────────────
describe('공개 GET(fetch) 계열 — URL·성공 반환·실패 throw', () => {
  const CASES = [
    ['fetchMacroIndicators', [], '/api/macro/indicators'],
    ['fetchMacroRegime', [], '/api/macro/regime'],
    ['fetchSiteStats', [], '/api/stats'],
    ['fetchMarketOutlook', [], '/api/macro/market-outlook'],
    ['fetchAnalystReports', ['005930'], '/api/detail/005930/analyst-reports'],
  ]
  for (const [fn, args, url] of CASES) {
    it(`${fn} → GET ${url}`, async () => {
      gfetch.mockResolvedValue(res({ ok: 1 }))
      await expect(api[fn](...args)).resolves.toEqual({ ok: 1 })
      expect(gfetch).toHaveBeenCalledWith(url)
    })
  }

  it('fetchMacroIndicatorHistory — months 쿼리(기본 12)·key 인코딩', async () => {
    gfetch.mockResolvedValue(res({}))
    await api.fetchMacroIndicatorHistory('vix')
    expect(gfetch).toHaveBeenCalledWith('/api/macro/indicators/vix/history?months=12')
    await api.fetchMacroIndicatorHistory('fear_greed', 60)
    expect(gfetch).toHaveBeenCalledWith('/api/macro/indicators/fear_greed/history?months=60')
  })

  it('fetchRegimeTrajectory — months 쿼리(기본 36)', async () => {
    gfetch.mockResolvedValue(res({}))
    await api.fetchRegimeTrajectory()
    expect(gfetch).toHaveBeenCalledWith('/api/macro/regime/history?months=36')
    await api.fetchRegimeTrajectory(24)
    expect(gfetch).toHaveBeenCalledWith('/api/macro/regime/history?months=24')
  })

  it('실패는 `API {status}` Error(status 프로퍼티 없음 — 기존 동작)', async () => {
    gfetch.mockResolvedValue(res({}, { ok: false, status: 503 }))
    const err = await api.fetchMacroRegime().catch((e) => e)
    expect(err.message).toBe('API 503')
    expect(err.status).toBeUndefined()
  })

  it('searchStocks — q 인코딩·limit, 반환은 data.results ?? []', async () => {
    gfetch.mockResolvedValue(res({ results: [{ ticker: '005930' }] }))
    await expect(api.searchStocks('삼성', 8)).resolves.toEqual([{ ticker: '005930' }])
    expect(gfetch).toHaveBeenCalledWith(
      `/api/stocks/search?q=${encodeURIComponent('삼성')}&limit=8`,
    )
    gfetch.mockResolvedValue(res({})) // results 키 없음 → []
    await expect(api.searchStocks('x')).resolves.toEqual([])
  })
})

// ── 패턴 B: 공개 POST(fetch, 바디 없음/JSON 바디) ────────────────────────────
describe('공개 POST(fetch) 계열', () => {
  const NOBODY = [
    ['recordVisit', [], '/api/visit'],
    ['fetchMarketOutlookSummary', [], '/api/macro/market-outlook/summary'],
    ['fetchNaverMarketOutlook', [15], '/api/macro/market-outlook/fetch?limit=15'],
    ['fetchAnalystReportsSummary', ['005930'], '/api/detail/005930/analyst-reports/summary'],
    ['fetchNaverReports', [20], '/api/reports/fetch?limit=20'],
    ['fetchNaverStockReports', ['005930', 10], '/api/detail/005930/analyst-reports/fetch?limit=10'],
  ]
  for (const [fn, args, url] of NOBODY) {
    it(`${fn} → POST ${url}(바디 없음)`, async () => {
      gfetch.mockResolvedValue(res({ n: 1 }))
      await expect(api[fn](...args)).resolves.toEqual({ n: 1 })
      expect(gfetch).toHaveBeenCalledWith(url, { method: 'POST' })
    })
  }

  it('setReportContext — JSON 바디(미지정은 null 로 정규화)', async () => {
    gfetch.mockResolvedValue(res({ ok: true }))
    await api.setReportContext('s1', '005930', 'r9')
    expect(gfetch).toHaveBeenCalledWith('/api/chat/report-context', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: 's1', ticker: '005930', report_id: 'r9' }),
    })
    await api.setReportContext('s1') // 해제 경로 — ticker/report_id null
    expect(gfetch).toHaveBeenLastCalledWith('/api/chat/report-context', expect.objectContaining({
      body: JSON.stringify({ session_id: 's1', ticker: null, report_id: null }),
    }))
  })

  it('setMarketOutlookContext / setViewContext — JSON 바디 계약', async () => {
    gfetch.mockResolvedValue(res({ ok: true }))
    await api.setMarketOutlookContext('s1', 'r2')
    expect(gfetch).toHaveBeenLastCalledWith('/api/chat/market-outlook-context', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ session_id: 's1', report_id: 'r2' }),
    }))
    await api.setViewContext('s1', 'balance', { a: 1 })
    expect(gfetch).toHaveBeenLastCalledWith('/api/chat/context', expect.objectContaining({
      body: JSON.stringify({ session_id: 's1', kind: 'balance', args: { a: 1 } }),
    }))
    await api.setViewContext('s1') // 핀 해제 — kind null·args {}
    expect(gfetch).toHaveBeenLastCalledWith('/api/chat/context', expect.objectContaining({
      body: JSON.stringify({ session_id: 's1', kind: null, args: {} }),
    }))
  })
})

// ── 패턴 C: 인증 GET(authFetch) ──────────────────────────────────────────────
describe('인증 GET(authFetch) 계열 — URL·성공 반환·실패 throw', () => {
  const CASES = [
    ['fetchStockBundle', ['005930'], '/api/detail/005930/bundle'],
    ['fetchConversations', [], '/api/conversations'],
    ['fetchConversationMessages', [7], '/api/conversations/7/messages'],
    ['fetchWatchlistMembership', ['005930'], '/api/watchlist/005930'],
    ['fetchReportHistory', ['005930'], '/api/detail/005930/report/history'],
    ['fetchBalance', [], '/api/balance'],
    ['fetchKisCredentialsStatus', [], '/api/me/kis-credentials'],
  ]
  for (const [fn, args, url] of CASES) {
    it(`${fn} → authFetch GET ${url}`, async () => {
      authFetch.mockResolvedValue(res({ d: 1 }))
      await expect(api[fn](...args)).resolves.toEqual({ d: 1 })
      expect(authFetch).toHaveBeenCalledWith(url)
    })
  }

  it('fetchStockChart — period/range 쿼리(기본 D/1y)', async () => {
    authFetch.mockResolvedValue(res({}))
    await api.fetchStockChart('005930')
    expect(authFetch).toHaveBeenCalledWith('/api/detail/005930/chart?period=D&range=1y')
    await api.fetchStockChart('005930', 'W', '10y')
    expect(authFetch).toHaveBeenCalledWith('/api/detail/005930/chart?period=W&range=10y')
  })

  it('fetchWatchlist — sortBy 없으면 쿼리 생략, 있으면 sort_by 인코딩', async () => {
    authFetch.mockResolvedValue(res({}))
    await api.fetchWatchlist()
    expect(authFetch).toHaveBeenCalledWith('/api/watchlist')
    await api.fetchWatchlist('near_target')
    expect(authFetch).toHaveBeenCalledWith('/api/watchlist?sort_by=near_target')
  })

  it('fetchScreener — market/size 쿼리(기본 all/30)', async () => {
    authFetch.mockResolvedValue(res({}))
    await api.fetchScreener()
    expect(authFetch).toHaveBeenCalledWith('/api/screener?market=all&size=30')
    await api.fetchScreener('kospi200', 40)
    expect(authFetch).toHaveBeenCalledWith('/api/screener?market=kospi200&size=40')
  })

  it('실패는 `API {status}` Error(status 프로퍼티 없음)', async () => {
    authFetch.mockResolvedValue(res({}, { ok: false, status: 401 }))
    const err = await api.fetchBalance().catch((e) => e)
    expect(err.message).toBe('API 401')
    expect(err.status).toBeUndefined()
  })
})

// ── 패턴 D: 인증 쓰기(authFetch POST/PATCH/DELETE) ───────────────────────────
describe('인증 쓰기(authFetch) 계열 — 메서드·바디·에러 shape', () => {
  it('createConversation — title 미지정은 null 바디', async () => {
    authFetch.mockResolvedValue(res({ id: 1 }))
    await api.createConversation()
    expect(authFetch).toHaveBeenCalledWith('/api/conversations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: null }),
    })
  })

  it('renameConversation → PATCH {title} / deleteConversation → DELETE', async () => {
    authFetch.mockResolvedValue(res({ ok: true }))
    await api.renameConversation(3, '새 이름')
    expect(authFetch).toHaveBeenLastCalledWith('/api/conversations/3', expect.objectContaining({
      method: 'PATCH',
      body: JSON.stringify({ title: '새 이름' }),
    }))
    await api.deleteConversation(3)
    expect(authFetch).toHaveBeenLastCalledWith('/api/conversations/3', { method: 'DELETE' })
  })

  it('postChat — {session_id, message} 바디', async () => {
    authFetch.mockResolvedValue(res({ text: '답', popups: [] }))
    await expect(api.postChat('s1', '안녕')).resolves.toEqual({ text: '답', popups: [] })
    expect(authFetch).toHaveBeenCalledWith('/api/chat', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ session_id: 's1', message: '안녕' }),
    }))
  })

  it('generateStockReport → POST(바디 없음)', async () => {
    authFetch.mockResolvedValue(res({ report: null }))
    await api.generateStockReport('005930')
    expect(authFetch).toHaveBeenCalledWith('/api/detail/005930/report', { method: 'POST' })
  })

  it('addWatchlist — 옵션 키는 값이 있을 때만 바디에 포함, 실패 err.status 부착(409 분기)', async () => {
    authFetch.mockResolvedValue(res({ ok: true }))
    await api.addWatchlist({ ticker: '005930', stockName: '삼성전자' })
    expect(authFetch).toHaveBeenCalledWith('/api/watchlist', expect.objectContaining({
      body: JSON.stringify({ ticker: '005930', stock_name: '삼성전자' }),
    }))
    authFetch.mockResolvedValue(res({}, { ok: false, status: 409 }))
    const err = await api.addWatchlist({ ticker: '005930' }).catch((e) => e)
    expect(err.message).toBe('API 409')
    expect(err.status).toBe(409) // addErrorMessage(status) 분기 계약
  })

  it('removeWatchlist / updateWatchlistTarget — err.status 부착·부분 PATCH 바디', async () => {
    authFetch.mockResolvedValue(res({ ok: true }))
    await api.updateWatchlistTarget('005930', { sell_target_price: 90000 })
    expect(authFetch).toHaveBeenLastCalledWith('/api/watchlist/005930', expect.objectContaining({
      method: 'PATCH',
      body: JSON.stringify({ sell_target_price: 90000 }), // 매도만 — 매수 키 미전송(부분 갱신)
    }))
    authFetch.mockResolvedValue(res({}, { ok: false, status: 404 }))
    const err = await api.removeWatchlist('005930').catch((e) => e)
    expect(err.status).toBe(404)
  })

  it('setKisCredentials — 실패 시 서버 detail 메시지 우선(없으면 API {status})', async () => {
    authFetch.mockResolvedValue(res({ detail: 'KIS 인증 실패' }, { ok: false, status: 400 }))
    await expect(api.setKisCredentials({ app_key: 'k' })).rejects.toThrow('KIS 인증 실패')
    authFetch.mockResolvedValue(resBadJson({ status: 500 })) // 바디 파싱 실패 → 기본 메시지
    await expect(api.setKisCredentials({})).rejects.toThrow('API 500')
    authFetch.mockResolvedValue(res({ ok: true, status: {} })) // 성공은 파싱된 JSON 그대로
    await expect(api.deleteKisCredentials()).resolves.toBeTruthy()
  })
})

// ── 패턴 E: 관리자(authFetch + err.status + detail) ──────────────────────────
describe('관리자 계열 — 403 분기용 err.status + detail 메시지', () => {
  it('fetchAdminUsers — users ?? [] 반환, 403 시 err.status', async () => {
    authFetch.mockResolvedValue(res({ users: [{ id: 1 }] }))
    await expect(api.fetchAdminUsers()).resolves.toEqual([{ id: 1 }])
    expect(authFetch).toHaveBeenCalledWith('/api/admin/users')
    authFetch.mockResolvedValue(res({}, { ok: false, status: 403 }))
    const err = await api.fetchAdminUsers().catch((e) => e)
    expect(err.status).toBe(403)
  })

  it('updateAdminUser — PATCH 바디·실패 detail+status(자기 관리자해제 400)', async () => {
    authFetch.mockResolvedValue(res({ id: 2, is_admin: true }))
    await api.updateAdminUser(2, { is_admin: true })
    expect(authFetch).toHaveBeenCalledWith('/api/admin/users/2', expect.objectContaining({
      method: 'PATCH',
      body: JSON.stringify({ is_admin: true }),
    }))
    authFetch.mockResolvedValue(res({ detail: '자기 자신은 해제 불가' }, { ok: false, status: 400 }))
    const err = await api.updateAdminUser(2, { is_admin: false }).catch((e) => e)
    expect(err.message).toBe('자기 자신은 해제 불가')
    expect(err.status).toBe(400)
  })

  it('resetAdminUserUsage → POST·err.status / deleteAdminUser → DELETE·detail+status', async () => {
    authFetch.mockResolvedValue(res({ id: 2 }))
    await api.resetAdminUserUsage(2)
    expect(authFetch).toHaveBeenLastCalledWith('/api/admin/users/2/reset-usage', { method: 'POST' })
    await api.deleteAdminUser(2)
    expect(authFetch).toHaveBeenLastCalledWith('/api/admin/users/2', { method: 'DELETE' })
    authFetch.mockResolvedValue(resBadJson({ status: 403 }))
    const err = await api.deleteAdminUser(2).catch((e) => e)
    expect(err.message).toBe('API 403')
    expect(err.status).toBe(403)
  })
})

// ── 패턴 F: SSE 스트림(리더 위임·실패는 onError 로만, throw 없음) ─────────────
describe('SSE 스트림 계열 — 리더 위임과 onError 폴백', () => {
  it('postChatStream — 성공 시 readChatStream(res, handlers) 위임', async () => {
    const r = res({})
    authFetch.mockResolvedValue(r)
    const handlers = { onToken: vi.fn() }
    await api.postChatStream('s1', 'msg', handlers)
    expect(readChatStream).toHaveBeenCalledWith(r, handlers)
  })

  it('postChatStream — 네트워크 실패는 throw 대신 onError(폴백 유도)', async () => {
    const boom = new Error('net down')
    authFetch.mockRejectedValue(boom)
    const onError = vi.fn()
    await api.postChatStream('s1', 'msg', { onError }) // reject 없이 완료돼야 한다
    expect(onError).toHaveBeenCalledWith(boom)
    expect(readChatStream).not.toHaveBeenCalled()
  })

  it('streamFetchStockReports / streamFetchMarketOutlook — URL·readSSE 위임·실패 onError', async () => {
    const r = res({})
    gfetch.mockResolvedValue(r)
    const onEvent = vi.fn(), onError = vi.fn()
    await api.streamFetchStockReports('005930', { onEvent, onError, limit: 10 })
    expect(gfetch).toHaveBeenCalledWith(
      '/api/detail/005930/analyst-reports/fetch/stream?limit=10', { method: 'POST' })
    expect(readSSE).toHaveBeenCalledWith(r, onEvent, onError)
    await api.streamFetchMarketOutlook({ onEvent, onError, limit: 15 })
    expect(gfetch).toHaveBeenLastCalledWith(
      '/api/macro/market-outlook/fetch/stream?limit=15', { method: 'POST' })
    gfetch.mockRejectedValue(new Error('down'))
    await api.streamFetchMarketOutlook({ onEvent, onError }) // throw 없이 onError
    expect(onError).toHaveBeenCalled()
  })
})
