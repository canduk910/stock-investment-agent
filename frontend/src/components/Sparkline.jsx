// 미니 스파크라인(공용) — 종가 시계열(points: number[]|null, 과거→현재)을 90×28 SVG 로 렌더.
// 관심종목·잔고 등 여러 패널이 공유한다. 데이터는 백엔드가 조회(환각 차단).
//   선색 = 방향색(상승 --c-up 빨강 / 하락 --c-down 파랑 / 보합 --c-flat) — theme.css 토큰만.
//   dir 을 주면 그 방향으로(관심종목=등락률 방향; null 이면 회색), **안 주면(undefined) 스파크 자체
//   추세**(마지막 종가 vs 첫 종가)로 방향을 자동 도출한다(잔고 미니차트).
//   points 결측·2점 미만이면 렌더하지 않는다(백엔드 per-item graceful → 조용히 생략).
export default function Sparkline({ points, dir, className = 'wl__spark' }) {
  if (!Array.isArray(points)) return null
  const nums = points.filter((p) => Number.isFinite(Number(p))).map(Number)
  if (nums.length < 2) return null
  const w = 90
  const h = 28
  const pad = 3
  const min = Math.min(...nums)
  const max = Math.max(...nums)
  const range = max - min || 1
  const stepX = (w - pad * 2) / (nums.length - 1)
  const coords = nums.map((p, i) => [
    pad + i * stepX,
    pad + (h - pad * 2) * (1 - (p - min) / range),
  ])
  const d = coords
    .map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`)
    .join(' ')
  const [ex, ey] = coords[coords.length - 1]
  // dir 미지정(undefined)이면 스파크 추세로 방향 도출(마지막>첫=up). dir 을 명시하면 그대로(null=회색).
  let trend = dir
  if (trend === undefined) {
    const last = nums[nums.length - 1]
    const first = nums[0]
    trend = last > first ? 'up' : last < first ? 'down' : 'flat'
  }
  const stroke =
    trend === 'up' ? 'var(--c-up)' : trend === 'down' ? 'var(--c-down)' : 'var(--c-flat)'
  return (
    <svg className={className} width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
      <path
        d={d}
        fill="none"
        stroke={stroke}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={ex} cy={ey} r="2.2" fill={stroke} />
    </svg>
  )
}
