import { describe, it, expect } from 'vitest'
import {
  SORT_KEYS,
  SORT_LABELS,
  sortItems,
  entrySignalLabel,
  detectTargetAlerts,
  addErrorMessage,
} from './watchlistLogic.js'

// 계약 근거(week-10 계획 §프론트 신규 watchlistLogic.js + 확정 API 계약):
//   items[].current_price/target_price/change_rate/distance_to_target/target_status/entry_signal.
//   정렬 3종은 chat/tools.py show_watchlist enum(SSOT)과 일치 — registered/change_rate/near_target.
//   진입 검토가능·목표가 도달/근접 = 강조(주황). 색은 컴포넌트가 토큰으로, 여기선 상태 문자열만.

describe('SORT_KEYS — chat/tools.py show_watchlist enum 과 일치(SSOT)', () => {
  it('정렬 키는 registered/change_rate/near_target 3종', () => {
    expect(SORT_KEYS).toEqual(['registered', 'change_rate', 'near_target'])
  })

  it('각 키에 한글 라벨이 있다(드롭다운 표기)', () => {
    for (const key of SORT_KEYS) {
      expect(typeof SORT_LABELS[key]).toBe('string')
      expect(SORT_LABELS[key].length).toBeGreaterThan(0)
    }
  })
})

describe('sortItems — 재조회 없이 프론트에서 재정렬(순수)', () => {
  const mk = (o) => ({
    ticker: o.t,
    added_at: o.added,
    change_rate: o.cr,
    distance_to_target: o.dist,
    target_price: o.target ?? null,
  })
  const A = mk({ t: '000001', added: '2026-07-01T00:00:00Z', cr: 1.0, dist: -1, target: 100 })
  const B = mk({ t: '000002', added: '2026-07-03T00:00:00Z', cr: 5.0, dist: -8, target: 100 })
  const C = mk({ t: '000003', added: '2026-07-02T00:00:00Z', cr: -2.0, dist: null, target: null })

  it('registered → added_at 오름차순(등록순, 원본 순서 안정)', () => {
    const out = sortItems([B, A, C], 'registered').map((x) => x.ticker)
    expect(out).toEqual(['000001', '000003', '000002'])
  })

  it('change_rate → 등락률 내림차순(높은 상승 먼저)', () => {
    const out = sortItems([A, B, C], 'change_rate').map((x) => x.ticker)
    expect(out).toEqual(['000002', '000001', '000003'])
  })

  it('near_target → distance 오름차순(매수관점: 더 하락=강한 신호 먼저)이되 목표가 없는(dist=null) 종목은 후순위', () => {
    // A dist=-1, B dist=-8 → B 가 목표가보다 더 내려와 매수 신호 강함(더 작은 값 먼저). null 은 맨 뒤.
    const out = sortItems([A, B, C], 'near_target').map((x) => x.ticker)
    expect(out).toEqual(['000002', '000001', '000003'])
  })

  it('원본 배열을 변형하지 않는다(불변)', () => {
    const input = [B, A, C]
    const snapshot = input.map((x) => x.ticker)
    sortItems(input, 'change_rate')
    expect(input.map((x) => x.ticker)).toEqual(snapshot)
  })

  it('미지의 sort_by 또는 비배열은 안전 처리(registered 로 폴백·[])', () => {
    expect(sortItems([B, A], 'unknown').map((x) => x.ticker)).toEqual(['000001', '000002'])
    expect(sortItems(null, 'registered')).toEqual([])
  })
})

describe('entrySignalLabel — 진입신호 배지 문구·톤(주황=검토가능, 회색=억제)', () => {
  it('국면 억제(entry_blocked) → "신규 진입 억제" · tone=muted', () => {
    const r = entrySignalLabel({ entry_blocked: true, entry_allowed: false })
    expect(r.text).toContain('억제')
    expect(r.tone).toBe('muted')
  })

  it('밸류에이션 초과(per_over/pbr_over) 이지만 국면 미차단 → "밸류에이션 부담" · tone=muted', () => {
    const r = entrySignalLabel({
      entry_blocked: false,
      per_over: true,
      pbr_over: false,
      entry_allowed: false,
    })
    expect(r.text).toMatch(/밸류에이션|부담/)
    expect(r.tone).toBe('muted')
  })

  it('국면 미차단 + 밸류에이션 이내(entry_allowed) → "검토 가능" · tone=emph(주황)', () => {
    const r = entrySignalLabel({
      entry_blocked: false,
      per_over: false,
      pbr_over: false,
      entry_allowed: true,
    })
    expect(r.text).toContain('검토')
    expect(r.tone).toBe('emph')
  })

  it('entry_signal 이 null(국면 판정 실패 등) → "판정 불가" · tone=muted(무한 스피너·임의 판단 금지)', () => {
    const r = entrySignalLabel(null)
    expect(r.tone).toBe('muted')
    expect(r.text.length).toBeGreaterThan(0)
  })
})

describe('detectTargetAlerts — 목표가 전이 알림(far → near/reached 일 때만 발화)', () => {
  const mk = (t, status) => ({ ticker: t, stock_name: t, target_status: status })

  it('far → near 전이면 알림 1건', () => {
    const prev = { '000001': 'far' }
    const alerts = detectTargetAlerts([mk('000001', 'near')], prev)
    expect(alerts).toHaveLength(1)
    expect(alerts[0].ticker).toBe('000001')
    expect(alerts[0].status).toBe('near')
  })

  it('far → reached 전이면 알림 1건', () => {
    const alerts = detectTargetAlerts([mk('000002', 'reached')], { '000002': 'far' })
    expect(alerts).toHaveLength(1)
    expect(alerts[0].status).toBe('reached')
  })

  it('이미 near/reached 상태 유지(near→near, reached→reached)는 재알림하지 않는다', () => {
    expect(detectTargetAlerts([mk('a', 'near')], { a: 'near' })).toEqual([])
    expect(detectTargetAlerts([mk('a', 'reached')], { a: 'reached' })).toEqual([])
  })

  it('near → far(멀어짐)·reached → far 는 알림 없음(악화 방향)', () => {
    expect(detectTargetAlerts([mk('a', 'far')], { a: 'near' })).toEqual([])
    expect(detectTargetAlerts([mk('a', 'far')], { a: 'reached' })).toEqual([])
  })

  it('reached ← near 승격(near→reached)도 전이 알림(더 강한 신호 도달)', () => {
    const alerts = detectTargetAlerts([mk('a', 'reached')], { a: 'near' })
    expect(alerts).toHaveLength(1)
    expect(alerts[0].status).toBe('reached')
  })

  it('이전 상태 미기록(신규 추가 종목)이면서 이미 near/reached 여도 알림 없음(초기 스팸 방지)', () => {
    // prevMap 에 없는 종목은 "방금 관측 시작" — far 로 간주해 near/reached 여도 발화하지 않는다.
    expect(detectTargetAlerts([mk('new1', 'near')], {})).toEqual([])
    expect(detectTargetAlerts([mk('new1', 'reached')], {})).toEqual([])
  })

  it('none 상태(목표가 없음)는 항상 알림 없음', () => {
    expect(detectTargetAlerts([mk('a', 'none')], { a: 'far' })).toEqual([])
  })

  it('prevMap 이 null/누락이어도 안전(초기 로드 — 알림 0)', () => {
    expect(detectTargetAlerts([mk('a', 'reached')], null)).toEqual([])
    expect(detectTargetAlerts([mk('a', 'near')], undefined)).toEqual([])
  })

  it('items 가 비배열이면 [](방어)', () => {
    expect(detectTargetAlerts(null, { a: 'far' })).toEqual([])
  })
})

describe('addErrorMessage — 관심종목 추가 실패 HTTP status → 안내 문구(graceful)', () => {
  // 계약(data-engineer): POST 상태코드 409(상한 30 초과)/400(불량 ticker)/404/422(target 음수).
  //   409 는 단순 안내(회색) — 주황(강조)·빨강(위험) 아님. 나머지도 회색 중립 안내.
  it('409 → 관심종목 상한(최대 30) 안내', () => {
    const m = addErrorMessage(409)
    expect(m).toMatch(/가득|최대|30/)
  })
  it('400 → 불량 종목코드 안내', () => {
    expect(addErrorMessage(400)).toMatch(/종목|코드/)
  })
  it('422 → 잘못된 값 안내', () => {
    expect(addErrorMessage(422)).toMatch(/값|목표가|올바/)
  })
  it('그 외/미상 status → 일반 실패 안내(무한 스피너·크래시 금지)', () => {
    expect(addErrorMessage(500).length).toBeGreaterThan(0)
    expect(addErrorMessage(null).length).toBeGreaterThan(0)
    expect(addErrorMessage(undefined).length).toBeGreaterThan(0)
  })
})
