import { useEffect, useState } from 'react'
import { fetchMacroIndicators } from '../api.js'
import { INDICATOR_ORDER } from '../indicatorMeta.js'
import IndicatorCard from './IndicatorCard.jsx'

export default function MacroDashboard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      setData(await fetchMacroIndicators())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const indicators = data?.indicators ?? {}
  const failed = data?.partial_failure ?? []

  return (
    <div className="dashboard">
      <header className="dashboard__header">
        <div>
          <h1>시장 국면 대시보드</h1>
          <p className="dashboard__subtitle">거시 지표 실시간 수집 · WEEK 06 데이터 파이프라인</p>
        </div>
        <button className="refresh" onClick={load} disabled={loading}>
          {loading ? '수집 중…' : '↻ 새로고침'}
        </button>
      </header>

      {/* WEEK 07 매크로 엔진이 연결될 국면 게이지 자리 */}
      <div className="gauge-placeholder">
        <span className="gauge-placeholder__badge">W07</span>
        <span>국면 판정 게이지 · 권장 현금비중 — 매크로 엔진 연결 예정</span>
      </div>

      {error && <div className="banner banner--error">API 오류: {error}</div>}
      {failed.length > 0 && (
        <div className="banner banner--warn">
          일부 지표 조회 실패: {failed.join(', ')} · 나머지는 정상 표시
        </div>
      )}

      <div className="grid">
        {INDICATOR_ORDER.map((id) => (
          <IndicatorCard key={id} id={id} point={indicators[id]} />
        ))}
      </div>

      <footer className="dashboard__footer">
        FRED · 야후/FRED(VIX) · CNN(공포탐욕) — 현재값은 매 요청 실시간 수집(캐시 없음, 원칙1)
      </footer>
    </div>
  )
}
