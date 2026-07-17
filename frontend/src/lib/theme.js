// klinecharts(캔버스)는 CSS var() 를 직접 못 쓰므로, theme.css 토큰의 '값'을 읽어 JS 로 넘긴다.
// 팔레트 SSOT 는 여전히 theme.css — 여기서는 읽기만 한다(색 하드코딩 아님).
// 주의: --c-up 같은 시맨틱 별칭은 `var(--c-blue)` 참조라 getComputedStyle 결과가 브라우저마다
//   다르다. 그래서 '구체 hex' 토큰(--c-blue 등)을 직접 읽고, 여기서 상승/하락 역할에 매핑한다.

// theme.css 와 동일한 폴백(토큰 조회 실패/테스트 환경 대비). 값이 바뀌면 theme.css 가 우선.
const FALLBACK = {
  '--c-blue': '#2563eb',
  '--c-blue-strong': '#1d4ed8',
  '--c-navy': '#16233d',
  '--c-text-secondary': '#55617a',
  '--c-text-muted': '#8a94a8',
  '--c-border': '#d8e0ea',
  '--c-border-strong': '#c2cdda',
  '--c-surface': '#ffffff',
  '--c-white': '#ffffff',
  '--c-emph': '#e0670f', // 주황 = 강조(대순환 단기선 등). 가격 방향색 아님.
  '--c-chart-up': '#e5322d', // 캔들 상승 = 빨강(한국 관습·차트 예외)
  '--c-chart-down': '#2563eb', // 캔들 하락 = 파랑
}

function readToken(cs, name) {
  const v = cs?.getPropertyValue(name)?.trim()
  return v || FALLBACK[name]
}

// 차트용 팔레트(예외) — 한국 시장 관습: 캔들 상승=빨강 / 하락=파랑.
// 지표선(MA/RSI)·오버레이는 남색·회색으로 캔들색과 구분한다(캔들 빨/파와 안 겹치게). 초록·황색 없음.
export function readChartPalette() {
  const cs =
    typeof window !== 'undefined' && typeof getComputedStyle === 'function'
      ? getComputedStyle(document.documentElement)
      : null
  const t = (name) => readToken(cs, name)
  return {
    up: t('--c-chart-up'), // 캔들 상승 = 빨강 (한국 시장 관습, 차트 한정 예외)
    down: t('--c-chart-down'), // 캔들 하락 = 파랑
    navy: t('--c-navy'),
    blueStrong: t('--c-blue-strong'),
    emph: t('--c-emph'), // 주황 = 강조(대순환 단기선). 가격 방향색(빨/파)과 구분.
    grid: t('--c-border'),
    border: t('--c-border'),
    borderStrong: t('--c-border-strong'),
    axisText: t('--c-text-secondary'),
    tooltipText: t('--c-text-secondary'),
    surface: t('--c-surface'),
    white: t('--c-white'),
  }
}
