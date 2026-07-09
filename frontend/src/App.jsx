import { useCallback, useEffect, useRef, useState } from 'react'
import MacroDashboard from './components/MacroDashboard.jsx'
import StockReport from './components/StockReport.jsx'
import WatchlistView from './components/WatchlistView.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import { detectTargetAlerts } from './lib/watchlistLogic.js'

// 자동 새로고침 간격 — KIS 레이트리밋 보호(리스트 enrich = 종목별 병렬 시세). 보수적으로 60s.
const REFRESH_MS = 60_000

// 능동 알림 배너 문구(주황=강조). 손실경고 아님 → 빨강 아님. "안내"만(주문 자동실행 없음).
function alertMessage(alerts) {
  const names = alerts.map((a) => `${a.stock_name}(${a.status === 'reached' ? '도달' : '근접'})`)
  return `목표가 ${names.join(', ')} — 관심종목을 확인해 보세요.`
}

export default function App() {
  // 워치리스트 자동 새로고침 트리거(값이 바뀌면 WatchlistView 가 재조회). 60s interval + 언마운트 clear.
  const [refreshKey, setRefreshKey] = useState(0)
  // 앱레벨 능동 알림 배너(주황). 목표가 far→near/reached 전이 시에만 표시.
  const [alertBanner, setAlertBanner] = useState(null)
  // 이전 관측 상태({ticker: target_status}) — 전이 감지 기준. 마운트 첫 관측은 알림 억제.
  const prevStatusRef = useRef(null)
  const notifiedRef = useRef(false) // 브라우저 알림 권한 요청은 최초 1회만.

  useEffect(() => {
    const id = setInterval(() => setRefreshKey((k) => k + 1), REFRESH_MS)
    return () => clearInterval(id) // 언마운트 시 정리(무한 타이머·중복 방지).
  }, [])

  // 브라우저 알림 발화(권한 있을 때만). 권한 미요청이면 최초 1회 요청하고 이후엔 조용히 스킵.
  const fireBrowserNotification = useCallback((alerts) => {
    if (typeof Notification === 'undefined') return
    const send = () => {
      try {
        new Notification('목표가 알림', { body: alertMessage(alerts) })
      } catch {
        /* 알림 실패는 조용히 무시 — 배너로 이미 안내됨 */
      }
    }
    if (Notification.permission === 'granted') {
      send()
    } else if (Notification.permission === 'default' && !notifiedRef.current) {
      notifiedRef.current = true
      Notification.requestPermission().then((perm) => {
        if (perm === 'granted') send()
      })
    }
    // 'denied' 는 배너만(브라우저 알림 스킵).
  }, [])

  // WatchlistView 가 새 view 를 받을 때마다 호출 — 전이 감지 → 배너 + 브라우저 알림.
  const onWatchlistView = useCallback(
    (view) => {
      const items = view?.items ?? []
      const alerts = detectTargetAlerts(items, prevStatusRef.current)
      if (alerts.length > 0) {
        setAlertBanner(alertMessage(alerts))
        fireBrowserNotification(alerts)
      }
      // 다음 비교를 위해 현재 상태 스냅샷 저장(ticker→target_status).
      prevStatusRef.current = Object.fromEntries(
        items.map((it) => [it.ticker, it.target_status]),
      )
    },
    [fireBrowserNotification],
  )

  return (
    <>
      <MacroDashboard />
      <StockReport />
      <section className="dashboard watchlist-page" aria-label="관심종목">
        <header className="dashboard__header">
          <div>
            <h1>관심종목</h1>
            <p className="dashboard__subtitle">
              신규 진입(살까·언제) 관점 · 시세·진입신호는 실시간 직접 조회(LLM 미개입) · 60초 자동 갱신
            </p>
          </div>
        </header>
        {alertBanner && (
          <div className="banner banner--emph watchlist-page__alert" role="status">
            {alertBanner}
            <button
              type="button"
              className="banner__retry"
              onClick={() => setAlertBanner(null)}
              aria-label="알림 닫기"
            >
              닫기
            </button>
          </div>
        )}
        <WatchlistView refreshKey={refreshKey} onView={onWatchlistView} />
      </section>
      <ChatPanel />
    </>
  )
}
