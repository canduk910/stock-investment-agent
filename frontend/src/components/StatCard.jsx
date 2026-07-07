// 순수 표현 카드 — 값·판정은 상위(백엔드 summary)가 확정하고, 여기선 표시만 한다.
// 기존 .card* CSS 를 재사용한다(IndicatorCard 는 매크로 전용이라 건드리지 않음).
// props: label, value, unit, badge({text}), sub, subDir('up'|'down'|'flat'), meta, muted.
export default function StatCard({ label, value, unit, badge, sub, subDir, meta, muted }) {
  const subClass = subDir === 'up' ? 'up' : subDir === 'down' ? 'down' : ''
  return (
    <div className="card">
      <div className="card__label">{label}</div>

      {badge ? (
        // 밸류에이션 라벨 등 — 남색 알약 하나로 통일(색으로 우열 암시 금지).
        <div className="stat-badge">{badge.text}</div>
      ) : (
        <div className={`card__value ${muted ? 'card__value--muted' : ''}`}>
          {value}
          {unit ? <span className="card__unit">{unit}</span> : null}
        </div>
      )}

      {sub ? <div className={`card__delta ${subClass}`}>{sub}</div> : <div className="card__delta"> </div>}
      {meta ? <div className="card__meta">{meta}</div> : null}
    </div>
  )
}
