// 워치리스트 표현·정렬 로직(순수) — 브라우저 없이 테스트 가능(watchlistLogic.test.js).
// 원칙: 숫자·진입신호 판정은 백엔드(watchlist/service.py + stock/summary.py::regime_gate)가 확정한다.
//   여기서는 "어떻게 정렬·표시할지"만 결정한다. target_status/distance/entry_signal 의 판정 계약은
//   백엔드와 동일해야 하므로(전이 알림의 클라이언트측 근거), 백엔드 _target_status 로직을 그대로 복제한다.
//
// 정렬 3종은 chat/tools.py show_watchlist enum(LLM-facing SSOT) = watchlist/constants.py SORT_KEYS 와 일치.

// 정렬 기준 — show_watchlist sort_by enum·SORT_KEYS 와 동일 순서(SSOT 일치 테스트로 강제).
export const SORT_KEYS = ['registered', 'change_rate', 'near_target']

export const SORT_LABELS = {
  registered: '등록순',
  change_rate: '등락률순',
  near_target: '목표가 근접순',
}

function isFiniteNum(v) {
  return typeof v === 'number' && Number.isFinite(v)
}

// (current-target)/target*100 (%). target 없음/0/음수/현재가 결측 → null(0 나눗셈·부호역전 방지).
// 백엔드 watchlist/service.py::_distance_to_target 과 동일 계약.
export function distanceToTarget(current, target) {
  if (!isFiniteNum(current)) return null
  if (!isFiniteNum(target) || target <= 0) return null
  return ((current - target) / target) * 100.0
}

// 매수 진입 관점: 목표가 = '사고 싶은 가격'. 현재가가 내려와 목표가에 근접·도달할수록 신호.
// 백엔드 watchlist/service.py::_target_status 와 동일 계약(능동 알림 전이 판정의 클라이언트측 근거).
//   none:    target 없음(또는 현재가 결측)
//   reached: current <= target(목표가 이하로 하락 도달)
//   near:    current <= target*(1+thr%)(목표가보다 thr% 이내로 근접)
//   far:     그 외(아직 목표가보다 thr% 초과로 높음)
export function classifyTargetStatus(current, target, thresholdPct) {
  if (!isFiniteNum(current)) return 'none'
  if (!isFiniteNum(target) || target <= 0) return 'none'
  if (current <= target) return 'reached'
  if (current <= target * (1.0 + thresholdPct / 100.0)) return 'near'
  return 'far'
}

// 비교자 3종 — 각각 (a,b)=>number. null/결측은 항상 후순위로 밀어낸다(NaN 비교 회피).
function cmpRegistered(a, b) {
  // added_at ISO8601 문자열 오름차순(등록순). 결측은 뒤로.
  const av = a?.added_at ?? ''
  const bv = b?.added_at ?? ''
  if (av === bv) return 0
  return av < bv ? -1 : 1
}

function cmpChangeRate(a, b) {
  // 등락률 내림차순(높은 상승 먼저). 결측은 뒤로.
  const av = isFiniteNum(a?.change_rate) ? a.change_rate : null
  const bv = isFiniteNum(b?.change_rate) ? b.change_rate : null
  if (av === null && bv === null) return 0
  if (av === null) return 1
  if (bv === null) return -1
  return bv - av
}

function cmpNearTarget(a, b) {
  // distance_to_target 오름차순(매수관점: 더 하락한=강한 신호 먼저). 목표가 없는(null) 종목은 후순위.
  const av = isFiniteNum(a?.distance_to_target) ? a.distance_to_target : null
  const bv = isFiniteNum(b?.distance_to_target) ? b.distance_to_target : null
  if (av === null && bv === null) return 0
  if (av === null) return 1
  if (bv === null) return -1
  return av - bv
}

const COMPARATORS = {
  registered: cmpRegistered,
  change_rate: cmpChangeRate,
  near_target: cmpNearTarget,
}

// items 를 sortBy 로 정렬한 새 배열 반환(원본 불변). 미지의 sortBy → registered 폴백. 비배열 → [].
export function sortItems(items, sortBy) {
  if (!Array.isArray(items)) return []
  const cmp = COMPARATORS[sortBy] ?? COMPARATORS.registered
  // Array.prototype.sort 는 안정 정렬(ES2019+) → 동률은 원본 순서 유지.
  return [...items].sort(cmp)
}

// 진입신호(entry_signal) → 배지 문구·톤. tone: 'emph'(주황=검토가능) | 'muted'(회색=억제/부담/불가).
// 위험(빨강) 은 쓰지 않는다 — 진입 억제는 위험이 아니라 "지금은 아님". 색은 컴포넌트가 토큰으로 매핑.
// 계약: entry_signal = {entry_blocked, per_over, pbr_over, single_cap, entry_allowed, note} | null.
export function entrySignalLabel(signal) {
  if (!signal) {
    // judgement 실패 등으로 진입 판정 불가(임의 판단·무한 스피너 금지).
    return { text: '진입 판정 불가', tone: 'muted' }
  }
  if (signal.entry_blocked) {
    // 국면 게이트(single_cap=0 등)로 신규진입 억제.
    return { text: '신규 진입 억제', tone: 'muted' }
  }
  if (signal.per_over || signal.pbr_over) {
    // 국면은 열려 있으나 종목 밸류에이션이 상한 초과.
    return { text: '밸류에이션 부담', tone: 'muted' }
  }
  if (signal.entry_allowed) {
    // 국면 미차단 + 밸류에이션 이내 → 검토 가능(강조 주황).
    return { text: '진입 검토 가능', tone: 'emph' }
  }
  return { text: '진입 판정 불가', tone: 'muted' }
}

// 목표가 능동 알림 — 이전 관측(prevMap: {ticker: target_status}) 대비 이번 items 에서
// far → near/reached 로 "개선 전이"한 종목만 골라 알림 대상으로 반환한다.
//   - 발화 조건: 이전이 far(또는 미관측=far 간주) 이고 이번이 near/reached.
//   - near → reached 승격도 전이로 본다(더 강한 매수 신호 도달).
//   - 유지(near→near, reached→reached)·악화(→far)·none 은 발화 안 함(스팸 방지).
//   - prevMap 이 없으면(초기 로드) 알림 0 — 마운트 직후 전 종목이 무더기로 울리는 걸 막는다.
// 반환: [{ticker, stock_name, status}] (App 이 배너·브라우저 Notification 발화에 사용).
const ALERT_STATUSES = new Set(['near', 'reached'])
export function detectTargetAlerts(items, prevMap) {
  if (!Array.isArray(items)) return []
  if (!prevMap) return [] // 초기 로드(비교 기준 없음) — 무더기 발화 방지.
  const out = []
  for (const it of items) {
    const status = it?.target_status
    if (!ALERT_STATUSES.has(status)) continue // none/far 는 애초에 알림 대상 아님.
    // 이전 상태가 이미 near/reached 였으면 재알림 안 함(유지). 미관측(prev 없음)은 far 로 간주.
    const prev = Object.prototype.hasOwnProperty.call(prevMap, it.ticker)
      ? prevMap[it.ticker]
      : undefined
    if (prev === undefined) continue // 신규 관측 — 초기 스팸 방지(far 취급).
    if (ALERT_STATUSES.has(prev)) {
      // near → reached 승격만 전이로 인정. near→near, reached→reached, reached→near 는 무시.
      if (prev === 'near' && status === 'reached') {
        out.push({ ticker: it.ticker, stock_name: it.stock_name ?? it.ticker, status })
      }
      continue
    }
    // prev 가 far(또는 none) → near/reached: 개선 전이.
    out.push({ ticker: it.ticker, stock_name: it.stock_name ?? it.ticker, status })
  }
  return out
}

// 관심종목 추가(POST) 실패 HTTP status → 사용자 안내 문구. graceful 처리(전체 에러 화면 금지).
// 계약(data-engineer): 409=상한 30 초과 / 400=불량 ticker / 404=미등록(PATCH) / 422=target 음수.
//   모두 단순 안내(회색 중립) — 상한 초과는 위험도 강조도 아니므로 주황·빨강 쓰지 않는다.
export function addErrorMessage(status) {
  switch (status) {
    case 409:
      return '관심종목이 가득 찼습니다(최대 30개). 기존 종목을 제거한 뒤 추가해 주세요.'
    case 400:
      return '종목 코드를 인식하지 못했습니다. 올바른 종목인지 확인해 주세요.'
    case 422:
      return '입력한 값이 올바르지 않습니다(목표가는 0 이상).'
    default:
      return '처리하지 못했습니다. 잠시 후 다시 시도해 주세요.'
  }
}
