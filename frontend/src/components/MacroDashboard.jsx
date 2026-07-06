import { useEffect, useState } from 'react'
import { fetchMacroIndicators } from '../api.js'
import { INDICATOR_ORDER } from '../indicatorMeta.js'
import IndicatorCard from './IndicatorCard.jsx'
import RegimeGauge from './RegimeGauge.jsx'

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
          <p className="dashboard__subtitle">거시 지표 실시간 수집 + 규칙 기반 국면 판정</p>
        </div>
        <button className="refresh" onClick={load} disabled={loading}>
          {loading ? '수집 중…' : '↻ 새로고침'}
        </button>
      </header>

      {/* WEEK 07 매크로 엔진 국면 게이지 — GET /api/macro/regime 소비(자체 로딩/에러 처리) */}
      <RegimeGauge />

      {error && <div className="banner banner--error">API 오류: {error}</div>}
      {failed.length > 0 && (
        <div className="banner banner--warn">
          일부 지표 조회 실패: {failed.join(', ')} · 나머지는 정상 표시
        </div>
      )}

      <h2 className="section-label">구성 지표</h2>
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
