// 숫자·방향 표시 포맷 SSOT — 컴포넌트가 로컬로 재정의하던 포맷터의 단일 출처.
// 값·판정은 백엔드가 확정하고 여기선 '표시 포맷'만(순수). 색은 theme.css 토큰이므로
// 방향 함수는 up/down/flat(또는 null)만 반환한다. **서로 다른 동작(% 유무·결측 fallback)은
// 이름을 달리해 각 원본 동작을 그대로 보존**한다(예: signedPct[%]≠signedNum[무%], changeDir[null]≠flatDir[flat]).

const _miss = (v) => v === null || v === undefined || !Number.isFinite(Number(v))

// 천단위 콤마(자릿수 고정 min=max=digits). 결측 → '—'.
export function num(v, digits = 0) {
  if (_miss(v)) return '—'
  return Number(v).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

// 원 단위 정수(천단위 콤마) + '원'. 결측 → '—'.
export function won(v) {
  if (_miss(v)) return '—'
  return `${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}원`
}

// 부호 있는 원(손익 금액). 결측 → '—'.
export function signedWon(v) {
  if (_miss(v)) return '—'
  const n = Number(v)
  return `${n > 0 ? '+' : ''}${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}원`
}

// 부호 있는 퍼센트(% 포함, 기본 2자리) — 수익률 등. 결측 → '—'.
export function signedPct(v, digits = 2) {
  if (_miss(v)) return '—'
  const n = Number(v)
  return `${n > 0 ? '+' : ''}${n.toFixed(digits)}%`
}

// 부호 있는 소수(% 없음, 기본 2자리) — 등락률 등 접미사 없이. 결측 → '—'.
export function signedNum(v, digits = 2) {
  if (_miss(v)) return '—'
  const n = Number(v)
  return `${n > 0 ? '+' : ''}${n.toFixed(digits)}`
}

// 소수(부호·% 없음, 기본 1자리). 결측 → '—'.
export function pct(v, digits = 1) {
  if (_miss(v)) return '—'
  return `${Number(v).toFixed(digits)}`
}

// 수량(정수, 천단위 콤마). 결측 → '—'.
export function qty(v) {
  if (_miss(v)) return '—'
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })
}

// 방향 → 글리프(▲▼─) — 색만으로 방향을 구분하지 않는 접근성 규칙의 표시 짝(팔레트 규칙).
// 인라인 삼항으로 7곳에 흩어져 있던 것을 단일화. up/down 외(flat/null/undefined)는 전부 '─'.
export function dirGlyph(dir) {
  return dir === 'up' ? '▲' : dir === 'down' ? '▼' : '─'
}

// 방향 → CSS 클래스('up'|'down'|'') — theme.css 방향색 토큰(.up/.down)과 짝.
// flat/결측은 빈 문자열(기본 회색) — 기존 각 컴포넌트 인라인 삼항과 동일 동작.
export function dirClass(dir) {
  return dir === 'up' ? 'up' : dir === 'down' ? 'down' : ''
}

// 방향(등락) — 결측이면 null(배지·글리프 생략). up/down/flat.
export function changeDir(v) {
  if (_miss(v)) return null
  return Number(v) > 0 ? 'up' : Number(v) < 0 ? 'down' : 'flat'
}

// 방향 — 결측이면 'flat'(항상 값). 잔고 손익 방향색용. up/down/flat.
export function flatDir(v) {
  if (_miss(v)) return 'flat'
  return Number(v) > 0 ? 'up' : Number(v) < 0 ? 'down' : 'flat'
}
