import { INDICATOR_META } from '../indicatorMeta.js'

function formatValue(v) {
  if (v === null || v === undefined) return '—'
  return Math.abs(v) >= 1000 ? Math.round(v).toLocaleString() : v.toFixed(2)
}

// point: 백엔드 IndicatorPoint({key,value,as_of,source,prev_value}) 또는 null.
export default function IndicatorCard({ id, point }) {
  const meta = INDICATOR_META[id] ?? { label: id, unit: '', hint: '' }

  // partial_failure: 해당 지표가 null 이면 나머지는 두고 이 카드만 안내 표시.
  if (!point) {
    return (
      <div className="card card--failed">
        <div className="card__label">{meta.label}</div>
        <div className="card__value card__value--muted">일시 조회 불가</div>
        <div className="card__meta">{meta.hint}</div>
      </div>
    )
  }

  const delta =
    point.prev_value !== null && point.prev_value !== undefined
      ? point.value - point.prev_value
      : null
  const dir = delta === null ? '' : delta > 0 ? '▲' : delta < 0 ? '▼' : '─'
  const dirClass = delta === null ? '' : delta > 0 ? 'up' : delta < 0 ? 'down' : ''

  return (
    <div className="card">
      <div className="card__label">{meta.label}</div>
      <div className="card__value">
        {formatValue(point.value)}
        <span className="card__unit">{meta.unit}</span>
      </div>
      <div className={`card__delta ${dirClass}`}>
        {delta !== null ? `${dir} 직전 ${formatValue(point.prev_value)}` : ' '}
      </div>
      <div className="card__meta">
        {meta.hint} · {point.source} · {point.as_of}
      </div>
    </div>
  )
}
