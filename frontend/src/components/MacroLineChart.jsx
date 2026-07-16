// 매크로 지표 월단위 라인차트(순수 SVG) — 카드 클릭 시 히스토리 오버레이에서 렌더.
//   points: [{date:"YYYY-MM-01", value:number}](과거→현재). thresholds:{lo,hi}(구간 가이드라인).
//   선색·마커는 방향색(--c-up/--c-down) 아님 — 남색 선 + 주황 현재값 + 회색 임계선(theme.css 토큰).
//   "이 값이 어느 구간(양호/중립/악화·탐욕/중립/공포)에 있는지"를 임계 가이드라인으로 보여준다.
// 데이터 2점 미만이면 렌더하지 않는다(오버레이가 "데이터 부족" 안내).

const W = 560
const H = 240
const PAD = { l: 46, r: 14, t: 16, b: 28 }

// "2025-11-01" → "25.11"(YY.MM). 파싱 실패는 원문.
function monthLabel(date) {
  const m = /^(\d{4})-(\d{2})/.exec(date || '')
  return m ? `${m[1].slice(2)}.${m[2]}` : date || ''
}

const fmt = (v, digits = 2) =>
  Number.isFinite(Number(v)) ? Number(v).toFixed(digits) : '—'

export default function MacroLineChart({ points, unit = '', thresholds }) {
  const data = (Array.isArray(points) ? points : []).filter((p) =>
    Number.isFinite(Number(p?.value)),
  )
  if (data.length < 2) return null

  const values = data.map((p) => Number(p.value))
  const lo = thresholds && Number.isFinite(Number(thresholds.lo)) ? Number(thresholds.lo) : null
  const hi = thresholds && Number.isFinite(Number(thresholds.hi)) ? Number(thresholds.hi) : null
  // y 도메인 = 데이터 + 임계선(가이드라인이 보이도록) + 여유.
  const domainVals = [...values, ...(lo != null ? [lo] : []), ...(hi != null ? [hi] : [])]
  let yMin = Math.min(...domainVals)
  let yMax = Math.max(...domainVals)
  if (yMax === yMin) yMax = yMin + 1
  const pad = (yMax - yMin) * 0.08
  yMin -= pad
  yMax += pad

  const innerW = W - PAD.l - PAD.r
  const innerH = H - PAD.t - PAD.b
  const xFor = (i) => PAD.l + (data.length === 1 ? innerW / 2 : (i / (data.length - 1)) * innerW)
  const yFor = (v) => PAD.t + (1 - (v - yMin) / (yMax - yMin)) * innerH

  const coords = values.map((v, i) => [xFor(i), yFor(v)])
  const linePath = coords
    .map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`)
    .join(' ')
  const [lastX, lastY] = coords[coords.length - 1]
  const lastVal = values[values.length - 1]

  // x축 라벨 — 과밀 방지로 최대 6개만.
  const step = Math.max(1, Math.ceil(data.length / 6))
  const xTicks = data
    .map((p, i) => ({ i, label: monthLabel(p.date) }))
    .filter(({ i }) => i % step === 0 || i === data.length - 1)

  return (
    <svg
      className="macro-chart"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="지표 월단위 히스토리 차트"
    >
      {/* y축 최소/최대 눈금 */}
      <text className="macro-chart__ytick" x={PAD.l - 6} y={PAD.t + 4} textAnchor="end">
        {fmt(yMax)}
      </text>
      <text className="macro-chart__ytick" x={PAD.l - 6} y={H - PAD.b} textAnchor="end">
        {fmt(yMin)}
      </text>

      {/* 임계 가이드라인(구간 경계) — 회색 점선 + 라벨 */}
      {[lo, hi].map((t, idx) =>
        t == null ? null : (
          <g key={idx}>
            <line
              className="macro-chart__guide"
              x1={PAD.l}
              x2={W - PAD.r}
              y1={yFor(t)}
              y2={yFor(t)}
            />
            <text className="macro-chart__guide-label" x={W - PAD.r} y={yFor(t) - 3} textAnchor="end">
              {fmt(t, 1)}
            </text>
          </g>
        ),
      )}

      {/* 값 라인 */}
      <path className="macro-chart__line" d={linePath} fill="none" />

      {/* 현재값(마지막 포인트) 강조 */}
      <circle className="macro-chart__last-dot" cx={lastX} cy={lastY} r="3.5" />
      <text className="macro-chart__last-val" x={lastX} y={lastY - 8} textAnchor="middle">
        {fmt(lastVal)}
        {unit}
      </text>

      {/* x축 월 라벨 */}
      {xTicks.map(({ i, label }) => (
        <text
          key={i}
          className="macro-chart__xtick"
          x={xFor(i)}
          y={H - PAD.b + 18}
          textAnchor="middle"
        >
          {label}
        </text>
      ))}
    </svg>
  )
}
