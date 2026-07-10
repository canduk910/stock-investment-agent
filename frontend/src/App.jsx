import { useCallback, useEffect, useRef, useState } from 'react'
import ChatPanel from './components/ChatPanel.jsx'
import RightPanel from './components/RightPanel.jsx'
import { fetchWatchlist } from './api.js'
import { detectTargetAlerts } from './lib/watchlistLogic.js'

// UX 개편 — 좌측 상시 채팅 + 우측 맥락형 동적 패널(모달 폐기). 2컬럼 그리드(.app__main).
//   우측 패널은 두 경로로 구동: (a) 챗봇 tool_call(ChatPanel.onShowPanel→setRightPanelSpec),
//   (b) 우측 퀵버튼(RightPanel.onSelect). 랜딩(기본)=관심종목.
// 목표가 능동 알림(IMP-11): 상시 마운트되던 WatchlistView 가 온디맨드로 바뀌어, 60s 폴링을 App 레벨로 이관.
//   App 이 fetchWatchlist 를 주기 호출→detectTargetAlerts(순수)로 전이 감지→앱레벨 주황 배너 + Notification.
//   → 우측 패널 내용과 무관하게 알림이 유지된다.

// 목표가 폴링 간격 — KIS 레이트리밋 보호(리스트 enrich = 종목별 병렬 시세). 보수적으로 60s.
const REFRESH_MS = 60_000

// 능동 알림 배너 문구(주황=강조). 손실경고 아님 → 빨강 아님. "안내"만(주문 자동실행 없음).
function alertMessage(alerts) {
  const names = alerts.map((a) => `${a.stock_name}(${a.status === 'reached' ? '도달' : '근접'})`)
  return `목표가 ${names.join(', ')} — 관심종목을 확인해 보세요.`
}

// 랜딩(기본) 우측 패널 = 관심종목(사용자 확정). valid:true(watchlist 는 항상 유효).
const LANDING_SPEC = { kind: 'watchlist', args: {}, valid: true }

export default function App() {
  // 우측 동적 패널 spec — 챗봇(onShowPanel)·퀵버튼(onSelect)이 리프팅. 닫으면 null(빈 상태).
  const [rightPanelSpec, setRightPanelSpec] = useState(LANDING_SPEC)

  // 앱레벨 능동 알림 배너(주황). 목표가 far→near/reached 전이 시에만 표시.
  const [alertBanner, setAlertBanner] = useState(null)
  // 이전 관측 상태({ticker: target_status}) — 전이 감지 기준. 마운트 첫 관측은 알림 억제.
  const prevStatusRef = useRef(null)
  // 브라우저 알림 권한 상태 — 요청은 사용자 제스처(CTA)에서만(IMP-11: interval 콜백 요청은 Safari/FF가 무시).
  const [notifPerm, setNotifPerm] = useState(
    typeof Notification !== 'undefined' ? Notification.permission : 'unsupported',
  )

  // 권한 요청은 사용자 제스처(CTA 버튼)에서만 — interval 콜백 안 요청은 브라우저가 무시(transient activation 필요).
  const enableNotifications = useCallback(() => {
    if (typeof Notification === 'undefined') return
    Notification.requestPermission().then((perm) => setNotifPerm(perm))
  }, [])

  // 브라우저 알림 발화 — 이미 granted 일 때만(여기서 권한 요청하지 않는다). 주황 배너는 항상 폴백.
  const fireBrowserNotification = useCallback((alerts) => {
    if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return
    try {
      new Notification('목표가 알림', { body: alertMessage(alerts) })
    } catch {
      /* 알림 실패는 조용히 무시 — 배너로 이미 안내됨 */
    }
  }, [])

  // 목표가 전이 감지 — 조회한 view 를 이전 스냅샷과 비교(순수 detectTargetAlerts 재사용).
  //   패널 내용과 무관하게 App 이 직접 폴링하므로, 우측이 잔고/국면이어도 알림은 유지된다.
  const checkTargetAlerts = useCallback(
    (items) => {
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

  // App 레벨 목표가 폴링 — 마운트 + 60s interval. 조회 실패는 조용히 무시(알림은 부가 기능, 화면 방해 없음).
  useEffect(() => {
    let cancelled = false
    async function poll() {
      try {
        const view = await fetchWatchlist()
        if (!cancelled) checkTargetAlerts(view?.items ?? [])
      } catch {
        /* 폴링 실패는 조용히 무시 — 우측 패널의 관심종목 뷰가 별도로 재시도 UI 를 제공한다 */
      }
    }
    poll() // 마운트 첫 관측(스냅샷 확보, 첫 회는 알림 억제)
    const id = setInterval(poll, REFRESH_MS)
    return () => {
      cancelled = true
      clearInterval(id) // 언마운트 시 정리(무한 타이머·중복 방지)
    }
  }, [checkTargetAlerts])

  return (
    <div className="app">
      <header className="app__topbar">
        <div>
          <h1 className="app__title">투자 분석 에이전트</h1>
          <p className="app__subtitle">
            좌측 채팅으로 물어보고 · 우측 패널에서 국면·관심종목·잔고·종목을 살펴보세요 · 판정·수치는
            코드가 결정(LLM 미개입)
          </p>
        </div>
        {notifPerm === 'default' ? (
          <button
            type="button"
            className="app__notif-cta"
            onClick={enableNotifications}
            title="목표가 도달·근접 시 브라우저 알림을 받습니다(주황 배너는 권한과 무관하게 항상 표시)."
          >
            목표가 알림 켜기
          </button>
        ) : null}
      </header>

      {alertBanner && (
        <div className="banner banner--emph app__alert" role="status">
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

      <main className="app__main">
        <div className="app__left">
          <ChatPanel onShowPanel={setRightPanelSpec} />
        </div>
        <div className="app__right">
          <RightPanel
            spec={rightPanelSpec}
            onSelect={setRightPanelSpec}
            onClose={() => setRightPanelSpec(null)}
          />
        </div>
      </main>
    </div>
  )
}
