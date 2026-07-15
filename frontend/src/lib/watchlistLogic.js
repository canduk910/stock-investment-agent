// 워치리스트 표현·정렬 로직(순수) — 브라우저 없이 테스트 가능(watchlistLogic.test.js).
// 원칙: 숫자·판정(target_status·distance_to_target)은 백엔드(watchlist/service.py)가 확정해 item 에
//   실어 내려준다. 프론트는 그 값을 "어떻게 정렬·표시할지"만 결정한다 — 백엔드 판정을 복제하지 않는다
//   (IMP-01: 죽은 복제 classifyTargetStatus/distanceToTarget 제거). 국면별 종목 진입신호(entry_signal)는
//   폐기(항목3 — 국면은 현금비중만 관리, 종목별 커트 없음).
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

// 매수·매도 중 목표선에 더 가까운 쪽의 |거리%|(둘 다 없으면 null). '목표가 근접순'은 이 값 오름차순.
function _proximity(it) {
  const cands = []
  if (isFiniteNum(it?.distance_to_target)) cands.push(Math.abs(it.distance_to_target))
  if (isFiniteNum(it?.sell_distance_to_target)) cands.push(Math.abs(it.sell_distance_to_target))
  return cands.length ? Math.min(...cands) : null
}

function cmpNearTarget(a, b) {
  // 매수·매도 중 더 가까운 목표선 기준 근접순(작은 |거리|=곧 도달 먼저). 목표가 없는 종목은 후순위.
  const av = _proximity(a)
  const bv = _proximity(b)
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

// 목표가 능동 알림 — 이전 관측(prevMap: {ticker: {buy, sell}}) 대비 이번 items 에서 매수·매도 각각
// far → near/reached 로 "개선 전이"한 신호만 골라 알림 대상으로 반환한다(side 부여).
//   - 발화 조건: 이전이 far/none(또는 미관측) 이고 이번이 near/reached.
//   - near → reached 승격도 전이로 본다(더 강한 신호 도달).
//   - 유지(near→near, reached→reached)·악화(→far)·none 은 발화 안 함(스팸 방지).
//   - prevMap 이 없으면(초기 로드) 알림 0. 신규 관측(prev 미기록)도 발화 안 함(초기 스팸 방지).
// 반환: [{ticker, stock_name, side:'buy'|'sell', status}] (App 이 배너·브라우저 Notification 에 사용).
const ALERT_STATUSES = new Set(['near', 'reached'])

// 한 side 의 이전(prev)→이번(status) 상태가 '개선 전이'인지. prev undefined=신규 관측(발화 안 함).
function _isImprovement(prev, status) {
  if (!ALERT_STATUSES.has(status)) return false // 이번이 near/reached 아니면 알림 대상 아님
  if (prev === undefined) return false // 신규 관측 — 초기 스팸 방지(far 취급하지 않고 억제)
  if (ALERT_STATUSES.has(prev)) return prev === 'near' && status === 'reached' // 승격만
  return true // far/none → near/reached
}

export function detectTargetAlerts(items, prevMap) {
  if (!Array.isArray(items)) return []
  if (!prevMap) return [] // 초기 로드(비교 기준 없음) — 무더기 발화 방지.
  const out = []
  for (const it of items) {
    const prev = Object.prototype.hasOwnProperty.call(prevMap, it.ticker)
      ? prevMap[it.ticker]
      : undefined
    const name = it?.stock_name ?? it.ticker
    if (_isImprovement(prev?.buy, it?.target_status)) {
      out.push({ ticker: it.ticker, stock_name: name, side: 'buy', status: it.target_status })
    }
    if (_isImprovement(prev?.sell, it?.sell_target_status)) {
      out.push({ ticker: it.ticker, stock_name: name, side: 'sell', status: it.sell_target_status })
    }
  }
  return out
}

// 관심종목 추가/제거/목표가 갱신 실패 HTTP status → 사용자 안내 문구. graceful(전체 에러 화면 금지).
// 계약: 409=상한 30 초과(추가) / 400=불량 ticker / 404=미등록(제거·PATCH) / 422=target 음수.
//   모두 단순 안내(회색 중립) — 상한 초과는 위험도 강조도 아니므로 주황·빨강 쓰지 않는다.
export function addErrorMessage(status) {
  switch (status) {
    case 409:
      return '관심종목이 가득 찼습니다(최대 30개). 기존 종목을 제거한 뒤 추가해 주세요.'
    case 400:
      return '종목 코드를 인식하지 못했습니다. 올바른 종목인지 확인해 주세요.'
    case 404:
      return '해당 관심종목을 찾지 못했습니다. 목록을 새로고침해 주세요.'
    case 422:
      return '입력한 값이 올바르지 않습니다(목표가는 0 이상).'
    default:
      return '처리하지 못했습니다. 잠시 후 다시 시도해 주세요.'
  }
}
