import { describe, it, expect } from 'vitest'
import {
  SORT_KEYS,
  SORT_LABELS,
  sortItems,
  detectTargetAlerts,
  addErrorMessage,
} from './watchlistLogic.js'

// 계약 근거(week-10 계획 §프론트 신규 watchlistLogic.js + 확정 API 계약):
//   items[].current_price/target_price/change_rate/distance_to_target/target_status.
//   정렬 3종은 chat/tools.py show_watchlist enum(SSOT)과 일치 — registered/change_rate/near_target.
//   목표가 도달/근접 = 강조(주황). 색은 컴포넌트가 토큰으로, 여기선 상태 문자열만.
//   국면별 종목 진입신호(entry_signal)는 폐기(항목3) — 관련 테스트 제거.

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

  it('near_target → 매수·매도 중 더 가까운 목표선 근접순(작은 |거리| 먼저), 목표가 없으면 후순위', () => {
    // A |dist|=1, B |dist|=8 → A 가 목표선에 더 가깝다(먼저). C 는 목표가 없음(맨 뒤).
    const out = sortItems([B, A, C], 'near_target').map((x) => x.ticker)
    expect(out).toEqual(['000001', '000002', '000003'])
  })

  it('near_target → 매도 목표가가 더 가까우면 그 |거리| 로 정렬(매수/매도 최소값)', () => {
    // X 는 매수 -20%(멀다)지만 매도 +1%(근접), Y 는 매수 -3%. X 의 최소 |거리|=1 < Y=3 → X 먼저.
    const X = { ticker: 'X', distance_to_target: -20, sell_distance_to_target: 1 }
    const Y = { ticker: 'Y', distance_to_target: -3, sell_distance_to_target: null }
    expect(sortItems([Y, X], 'near_target').map((x) => x.ticker)).toEqual(['X', 'Y'])
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

describe('detectTargetAlerts — 매수/매도 목표가 전이 알림(far → near/reached 일 때만, side 부여)', () => {
  // 스냅샷 계약: prevMap = {ticker: {buy, sell}}. item 은 target_status(매수)·sell_target_status(매도).
  const mk = (t, buy, sell = 'none') => ({
    ticker: t, stock_name: t, target_status: buy, sell_target_status: sell,
  })
  const prev = (buy, sell = 'none') => ({ buy, sell })

  it('매수 far → near 전이면 알림 1건(side=buy)', () => {
    const alerts = detectTargetAlerts([mk('000001', 'near')], { '000001': prev('far') })
    expect(alerts).toHaveLength(1)
    expect(alerts[0]).toMatchObject({ ticker: '000001', side: 'buy', status: 'near' })
  })

  it('매수 far → reached 전이면 알림 1건', () => {
    const alerts = detectTargetAlerts([mk('000002', 'reached')], { '000002': prev('far') })
    expect(alerts).toHaveLength(1)
    expect(alerts[0]).toMatchObject({ side: 'buy', status: 'reached' })
  })

  it('매수 유지(near→near, reached→reached)는 재알림하지 않는다', () => {
    expect(detectTargetAlerts([mk('a', 'near')], { a: prev('near') })).toEqual([])
    expect(detectTargetAlerts([mk('a', 'reached')], { a: prev('reached') })).toEqual([])
  })

  it('매수 악화(near→far·reached→far)는 알림 없음', () => {
    expect(detectTargetAlerts([mk('a', 'far')], { a: prev('near') })).toEqual([])
    expect(detectTargetAlerts([mk('a', 'far')], { a: prev('reached') })).toEqual([])
  })

  it('매수 near→reached 승격도 전이 알림', () => {
    const alerts = detectTargetAlerts([mk('a', 'reached')], { a: prev('near') })
    expect(alerts).toHaveLength(1)
    expect(alerts[0]).toMatchObject({ side: 'buy', status: 'reached' })
  })

  it('신규 관측(prev 미기록)이면 near/reached 여도 알림 없음(초기 스팸 방지)', () => {
    expect(detectTargetAlerts([mk('new1', 'near')], {})).toEqual([])
    expect(detectTargetAlerts([mk('new1', 'reached')], {})).toEqual([])
  })

  it('none 상태(목표가 없음)는 매수·매도 모두 알림 없음', () => {
    expect(detectTargetAlerts([mk('a', 'none', 'none')], { a: prev('far', 'far') })).toEqual([])
  })

  it('prevMap 이 null/누락이어도 안전(초기 로드 — 알림 0)', () => {
    expect(detectTargetAlerts([mk('a', 'reached')], null)).toEqual([])
    expect(detectTargetAlerts([mk('a', 'near')], undefined)).toEqual([])
  })

  it('items 가 비배열이면 [](방어)', () => {
    expect(detectTargetAlerts(null, { a: prev('far') })).toEqual([])
  })

  // ── 매도(sell) 전이 — 매수와 독립 ──
  it('매도 far → reached 전이면 알림 1건(side=sell)', () => {
    const alerts = detectTargetAlerts([mk('a', 'none', 'reached')], { a: prev('none', 'far') })
    expect(alerts).toHaveLength(1)
    expect(alerts[0]).toMatchObject({ side: 'sell', status: 'reached' })
  })

  it('매도 far → near 전이면 알림 1건(side=sell)', () => {
    const alerts = detectTargetAlerts([mk('a', 'none', 'near')], { a: prev('none', 'far') })
    expect(alerts).toHaveLength(1)
    expect(alerts[0].side).toBe('sell')
  })

  it('매도 유지(reached→reached)는 재알림 없음', () => {
    expect(
      detectTargetAlerts([mk('a', 'none', 'reached')], { a: prev('none', 'reached') }),
    ).toEqual([])
  })

  it('매수·매도 동시 전이면 2건(각 side)', () => {
    const alerts = detectTargetAlerts([mk('a', 'near', 'reached')], { a: prev('far', 'far') })
    expect(alerts).toHaveLength(2)
    expect(alerts.map((x) => x.side).sort()).toEqual(['buy', 'sell'])
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
  it('404 → 미등록 종목 안내(제거/목표가 갱신 실패, IMP-10)', () => {
    expect(addErrorMessage(404)).toMatch(/찾|목록|없/)
  })
  it('그 외/미상 status → 일반 실패 안내(무한 스피너·크래시 금지)', () => {
    expect(addErrorMessage(500).length).toBeGreaterThan(0)
    expect(addErrorMessage(null).length).toBeGreaterThan(0)
    expect(addErrorMessage(undefined).length).toBeGreaterThan(0)
  })
})
