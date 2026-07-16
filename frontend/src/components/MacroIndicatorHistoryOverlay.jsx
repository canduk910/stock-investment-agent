import { useEffect, useRef, useState } from 'react'
import { fetchMacroIndicatorHistory } from '../api.js'
import MacroLineChart from './MacroLineChart.jsx'

// 판정근거 지표 카드 클릭 → 최근 1년 월단위 히스토리 오버레이.
// MarketOutlookDetailOverlay 패턴 재사용(딤 배경·Esc/✕/배경 클릭 닫힘·role=dialog·닫기 포커스·
// 배경 스크롤 잠금 — 이 프로젝트의 모달 폐기 관습의 의도적 예외, 시황 상세와 동일). 범용 Modal 부활 아님.
// 열릴 때 서버에서 히스토리 조회(프론트 신뢰전송 없음). 미제공(fear_greed 등)은 graceful 안내.
export default function MacroIndicatorHistoryOverlay({ indicator, onClose }) {
  const closeRef = useRef(null)
  const [state, setState] = useState('loading') // loading | ready | error
  const [hist, setHist] = useState(null)

  useEffect(() => {
    closeRef.current?.focus() // 열릴 때 닫기 버튼 포커스(접근성)
    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden' // 배경 스크롤 잠금
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [onClose])

  useEffect(() => {
    let cancelled = false
    setState('loading')
    fetchMacroIndicatorHistory(indicator.key, 12)
      .then((h) => {
        if (!cancelled) {
          setHist(h)
          setState('ready')
        }
      })
      .catch(() => {
        if (!cancelled) setState('error')
      })
    return () => {
      cancelled = true
    }
  }, [indicator.key])

  const points = hist?.points ?? []
  const available = Boolean(hist?.available) && points.length >= 2

  return (
    <div className="mo-overlay" onClick={onClose}>
      <div
        className="mo-overlay__card mo-overlay__card--wide"
        role="dialog"
        aria-modal="true"
        aria-label={`${indicator.label} 최근 1년 히스토리`}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="mo-overlay__head">
          <div className="mo-overlay__meta">
            <span className="mo-card__broker">{indicator.label}</span>
            <span className="analyst__date">최근 1년 · 월단위</span>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="mo-overlay__close"
            onClick={onClose}
            aria-label="닫기"
          >
            ✕
          </button>
        </header>

        {state === 'loading' ? (
          <div className="popup__state">히스토리 불러오는 중…</div>
        ) : state === 'error' ? (
          <div className="popup__state">히스토리를 불러오지 못했습니다.</div>
        ) : available ? (
          <>
            <MacroLineChart points={points} unit={hist.unit} thresholds={hist.thresholds} />
            <p className="macro-hist__note" role="note">
              출처 {hist.source} · 회색 점선 = 구간 경계(양호/중립/악화·탐욕/중립/공포). 원천 데이터이며
              국면 판정은 코드가 별도로 합니다(참고용).
            </p>
          </>
        ) : (
          <div className="popup__state">
            {hist?.note || '이 지표는 히스토리를 제공하지 못했습니다(현재값만 참고하세요).'}
          </div>
        )}
      </div>
    </div>
  )
}
