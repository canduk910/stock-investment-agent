import { useRef, useState } from 'react'
import MacroIndicatorHistoryOverlay from './MacroIndicatorHistoryOverlay.jsx'

// 국면 판정 근거 4지표 카드 — 값 + 구간(양호/중립/악화·탐욕/중립/공포) + 축. 카드 클릭 → 최근 1년 히스토리.
//   데이터는 백엔드 breakdown(fetchMacroRegime.indicator_breakdown)에서 온다(프론트 임계 복제 없음).
//   색: 구간이 '중립' 아니면 주황 강조 소프트(=신호에 주목), 중립/결측은 회색. 방향(양호/공포)은 텍스트로.
//   가격 방향색(--c-up/--c-down)·경보 빨강(--c-danger)은 쓰지 않는다(주황=강조 규칙).
const AXIS_ORDER = ['경기', '심리']

// 구간 → 톤. 신호(중립 아님)=강조 주황, 중립=회색, 결측=흐린 회색.
function zoneTone(zone) {
  if (!zone) return 'muted'
  return zone === '중립' ? 'neutral' : 'signal'
}

// 값 포맷 — 큰 수(공포탐욕 등)는 정수, 작은 수(금리차·스프레드)는 소수 2자리. 단위 병기.
function formatValue(value, unit) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '데이터 없음'
  const n = Number(value)
  const s = Math.abs(n) >= 100 ? n.toFixed(0) : n.toFixed(2)
  return `${s}${unit || ''}`
}

function IndicatorCard({ item, onOpen }) {
  const tone = zoneTone(item.zone)
  return (
    <button
      type="button"
      className="macro-card"
      onClick={() => onOpen(item)}
      aria-label={`${item.label} 최근 1년 히스토리 보기`}
    >
      <span className="macro-card__name">{item.label}</span>
      <span className="macro-card__value">{formatValue(item.value, item.unit)}</span>
      <span className={`macro-card__zone macro-card__zone--${tone}`}>{item.zone || '—'}</span>
      <span className="macro-card__more" aria-hidden="true">1년 추이 ▸</span>
    </button>
  )
}

export default function MacroIndicatorCards({ breakdown }) {
  const [selected, setSelected] = useState(null)
  const triggerRef = useRef(null)
  const items = Array.isArray(breakdown) ? breakdown : []
  if (items.length === 0) return null

  function open(item) {
    triggerRef.current = document.activeElement // 트리거 카드 기억(닫을 때 포커스 복원)
    setSelected(item)
  }
  function close() {
    setSelected(null)
    triggerRef.current?.focus?.()
  }

  const byAxis = { 경기: [], 심리: [] }
  items.forEach((it) => {
    if (byAxis[it.axis]) byAxis[it.axis].push(it)
    else (byAxis[it.axis] = byAxis[it.axis] || []).push(it)
  })

  return (
    <div className="macro-cards">
      <div className="macro-cards__label">
        판정 근거 지표 <span className="macro-cards__hint">클릭 → 최근 1년 추이</span>
      </div>
      {AXIS_ORDER.map((axis) => {
        const list = byAxis[axis]
        if (!list || list.length === 0) return null
        return (
          <div key={axis} className="macro-cards__axis-group">
            <div className="macro-cards__axis">{axis}</div>
            <div className="macro-cards__grid">
              {list.map((it) => (
                <IndicatorCard key={it.key} item={it} onOpen={open} />
              ))}
            </div>
          </div>
        )
      })}
      {selected ? (
        <MacroIndicatorHistoryOverlay indicator={selected} onClose={close} />
      ) : null}
    </div>
  )
}
