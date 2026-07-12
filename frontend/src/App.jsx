import { useCallback, useEffect, useRef, useState } from 'react'
import ChatPanel from './components/ChatPanel.jsx'
import RightPanel from './components/RightPanel.jsx'
import LoginScreen from './components/LoginScreen.jsx'
import {
  fetchWatchlist,
  fetchMacroRegime,
  setReportContext,
  setViewContext,
  fetchConversations,
  createConversation,
} from './api.js'
import { fetchMe, logout } from './auth.js'
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

// 데이터 보유 패널 kind — 챗 세션 핀 컨텍스트 대상(백엔드 view_context.DATA_BEARING_KINDS 와 SSOT 일치).
// macro_dashboard(국면은 이미 프롬프트)·manage_watchlist(제안 액션)는 제외 → 전환 시 kind=null 로 해제.
const VIEW_CONTEXT_KINDS = new Set(['watchlist', 'balance', 'stock_report'])
// 패널 변경 → 컨텍스트 핀 디바운스(ms) — 빠른 탭 전환 시 KIS 재조회 폭주 방지.
const VIEW_CONTEXT_DEBOUNCE_MS = 400

// DK 모노그램 CI — 남색 스퀘어(rx) + 우상단 주황 다이아몬드 + 중앙 흰 "DK". 색은 theme.css 토큰.
function DkMonogram() {
  return (
    <svg
      className="app__monogram"
      width="34"
      height="34"
      viewBox="0 0 34 34"
      role="img"
      aria-label="디케이 투자에이전트 로고"
    >
      <rect x="0" y="0" width="34" height="34" rx="9" fill="var(--c-navy)" />
      <rect
        x="24.5"
        y="3.5"
        width="6"
        height="6"
        rx="1"
        fill="var(--c-emph)"
        transform="rotate(45 27.5 6.5)"
      />
      <text
        x="17"
        y="17"
        textAnchor="middle"
        dominantBaseline="central"
        fill="var(--c-white)"
        fontSize="13.5"
        fontWeight="900"
        letterSpacing="0.5"
      >
        DK
      </text>
    </svg>
  )
}

export default function App() {
  // 인증 게이트 — 마운트 시 토큰으로 fetchMe. user 없으면 LoginScreen(전체 게이트). null=확인 전.
  const [user, setUser] = useState(null)
  const [authChecked, setAuthChecked] = useState(false)
  useEffect(() => {
    let cancelled = false
    fetchMe()
      .then((u) => {
        if (!cancelled) setUser(u)
      })
      .finally(() => {
        if (!cancelled) setAuthChecked(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // 대화기록 — 유저별 대화 목록 + 현재 대화. 챗 session_id = conversation.id(문자열).
  const [conversations, setConversations] = useState([])
  const [conversationId, setConversationId] = useState(null)

  // 로그인 후 대화 목록 로드 + 최소 1개 보장(없으면 생성). 최근 대화를 현재로.
  useEffect(() => {
    if (!user) return
    let cancelled = false
    ;(async () => {
      try {
        let list = (await fetchConversations()).conversations || []
        if (list.length === 0) list = [await createConversation()]
        if (!cancelled) {
          setConversations(list)
          setConversationId(list[0].id)
        }
      } catch {
        /* 대화 로드 실패 — 챗은 이후 재시도(무한 에러 화면 금지) */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [user])

  const newConversation = useCallback(async () => {
    try {
      const c = await createConversation()
      setConversations((cs) => [c, ...cs])
      setConversationId(c.id)
    } catch {
      /* graceful */
    }
  }, [])

  const selectConversation = useCallback((id) => setConversationId(id), [])

  // 챗·컨텍스트 공유 session_id = 현재 대화 id(문자열). 대화 로드 전엔 null(가드).
  const sessionId = { current: conversationId != null ? String(conversationId) : null }

  const handleLogout = useCallback(() => {
    logout()
    setUser(null)
    setConversations([])
    setConversationId(null)
  }, [])

  // 우측 동적 패널 spec — 챗봇(onShowPanel)·퀵버튼(onSelect)이 리프팅. 닫으면 null(빈 상태).
  const [rightPanelSpec, setRightPanelSpec] = useState(LANDING_SPEC)

  // 리포트 상담 컨텍스트 배너 — 우측 리포트에서 "이 리포트로 상담하기"를 누르면 {broker} 세팅.
  //   좌측 챗 상단에 "○○증권 리포트로 상담 중" 배너를 띄우고, 이후 후속 질문은 그 리포트 근거로 답변.
  const [consult, setConsult] = useState(null)

  // 상담 시작 — AnalystReportsSection 이 setReportContext(서버 세팅) 성공 후 broker 를 올린다.
  const startConsult = useCallback((broker) => setConsult({ broker: broker || '' }), [])

  // 상담 종료 — 세션 컨텍스트 해제(서버) + 배너 제거. 실패해도 배너는 내린다(로컬 상태 우선).
  const endConsult = useCallback(() => {
    setReportContext(sessionId.current, null, null).catch(() => {})
    setConsult(null)
  }, [])

  // 톱바 상태 칩용 국면 — App 이 자체 조회(환각 차단). 실패해도 앱은 렌더(칩만 조용히 생략).
  const [regime, setRegime] = useState(null)

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

  // 현재 보고 있는 우측 패널 → 챗 세션 핀 컨텍스트(P1). 패널 변경 시 서버가 그 화면을 재조회해 스냅샷 고정
  //   → 이후 챗 질문이 그 데이터를 근거로 답한다. 데이터 kind 만 대상, 비데이터/무효는 kind=null 로 해제.
  //   디바운스(빠른 탭전환 KIS 폭주 방지) + 중복 kind+args 스킵(불필요 재조회 방지) + fire-and-forget.
  const lastViewCtxRef = useRef(null)
  useEffect(() => {
    if (conversationId == null) return // 대화(session) 준비 전엔 핀 스킵
    const spec = rightPanelSpec
    const kind =
      spec && spec.valid !== false && VIEW_CONTEXT_KINDS.has(spec.kind) ? spec.kind : null
    const key = kind ? `${kind}:${JSON.stringify(spec.args || {})}` : 'none'
    if (lastViewCtxRef.current === key) return // 동일 화면 재핀 방지(무관 리렌더·중복)
    lastViewCtxRef.current = key
    const id = setTimeout(() => {
      // 핀 실패는 UI 를 막지 않는다(부가 기능) — endConsult 와 동일 fire-and-forget.
      setViewContext(String(conversationId), kind, spec?.args || {}).catch(() => {})
    }, VIEW_CONTEXT_DEBOUNCE_MS)
    return () => clearTimeout(id)
  }, [rightPanelSpec, conversationId])

  // 톱바 상태 칩용 국면 — 마운트 1회 자체 조회(RegimeGauge 와 동일 패턴). 실패는 조용히 무시(칩만 생략).
  useEffect(() => {
    let cancelled = false
    fetchMacroRegime()
      .then((view) => {
        if (!cancelled) setRegime(view)
      })
      .catch(() => {
        /* 국면 조회 실패 — 톱바 칩만 생략하고 앱은 정상 렌더(전체 에러 화면 금지) */
      })
    return () => {
      cancelled = true
    }
  }, [])

  // 인증 게이트(모든 훅 뒤) — 확인 전엔 아무것도, 비로그인은 LoginScreen(전체 게이트).
  if (!authChecked) return null
  if (!user) return <LoginScreen onAuthed={setUser} />

  return (
    <div className="app">
      <header className="app__topbar">
        <div className="app__brand">
          <DkMonogram />
          <div className="app__brand-text">
            <h1 className="app__title">디케이 투자에이전트</h1>
            <p className="app__caption">DK INVESTMENT AGENT</p>
          </div>
        </div>

        <div className="app__status">
          <span className="app__user" title={user.email}>
            {user.email}
          </span>
          <button type="button" className="app__logout" onClick={handleLogout}>
            로그아웃
          </button>
          {regime ? (
            <>
              <span className="app__chip app__chip--regime">
                현재 국면 · {regime.regime}
              </span>
              {regime.recommended_cash_ratio != null ? (
                <span className="app__chip app__chip--cash">
                  권장 현금비중 <b>{regime.recommended_cash_ratio}%</b>
                </span>
              ) : null}
              {regime.vix_panic ? (
                <span className="app__chip app__chip--panic">⚠ VIX 패닉</span>
              ) : null}
            </>
          ) : null}
          {notifPerm === 'granted' ? (
            <span className="app__notif-cta app__notif-cta--on" role="status">
              ✓ 알림 켜짐
            </span>
          ) : notifPerm === 'default' ? (
            <button
              type="button"
              className="app__notif-cta"
              onClick={enableNotifications}
              title="목표가 도달·근접 시 브라우저 알림을 받습니다(주황 배너는 권한과 무관하게 항상 표시)."
            >
              목표가 알림 켜기
            </button>
          ) : null}
        </div>
      </header>

      {alertBanner && (
        <div className="banner banner--emph app__alert" role="status">
          <span className="app__alert-text">{alertBanner}</span>
          <span className="app__alert-actions">
            <button
              type="button"
              className="app__alert-view"
              onClick={() => {
                setRightPanelSpec(LANDING_SPEC)
                setAlertBanner(null)
              }}
            >
              관심종목 보기
            </button>
            <button
              type="button"
              className="banner__retry"
              onClick={() => setAlertBanner(null)}
              aria-label="알림 닫기"
            >
              닫기
            </button>
          </span>
        </div>
      )}

      <main className="app__main">
        <div className="app__left">
          <ChatPanel
            sessionId={sessionId.current}
            onShowPanel={setRightPanelSpec}
            consult={consult}
            onEndConsult={endConsult}
            conversations={conversations}
            conversationId={conversationId}
            onNewConversation={newConversation}
            onSelectConversation={selectConversation}
          />
        </div>
        <div className="app__right">
          <RightPanel
            spec={rightPanelSpec}
            onSelect={setRightPanelSpec}
            onClose={() => setRightPanelSpec(null)}
            sessionId={sessionId.current}
            onConsult={startConsult}
          />
        </div>
      </main>
    </div>
  )
}
