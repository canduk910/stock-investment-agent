import { useEffect, useRef, useState } from 'react'
import { isValidTicker } from '../lib/ticker.js'
import PopupStockReport from './PopupStockReport.jsx'
import PopupWatchlist from './PopupWatchlist.jsx'
import ManageWatchlistConfirm from './ManageWatchlistConfirm.jsx'
import RegimeGauge from './RegimeGauge.jsx'
import MarketOutlookSection from './MarketOutlookSection.jsx'
import BalancePanel from './BalancePanel.jsx'

// 우측 동적 패널(리디자인) — 좌측 상시 채팅 옆에서 맥락형 콘텐츠를 인라인 렌더한다(모달 폐기).
// 두 경로로 구동: (a) 챗봇 tool_call(App 이 onShowPanel 로 spec 리프팅) · (b) 상단 세그먼트 탭·종목검색(대화 없이 직접 탐색).
// 팝업 컴포넌트는 전부 모달 비종속·자체조회형이라 여기 그대로 인라인 재사용한다(재작성 0) —
//   실데이터·partial_failure 는 각 컴포넌트가 API 로 직접 조회(환각 차단). 이 파일은 라우팅·틀만 담당.
// 색은 theme.css 토큰만.

// spec.kind → 헤더 제목. stock_report 는 종목명이 있으면 "{종목명} · 제목"으로 구성(본문에서 처리).
const PANEL_TITLE = {
  stock_report: '종목 종합리포트',
  macro_dashboard: '시장 국면 대시보드',
  watchlist: '관심종목',
  manage_watchlist: '관심종목 관리',
  balance: '내 잔고',
}

// 세그먼트 탭(SSOT) — 대화 없이 직접 탐색. 클릭 시 해당 kind spec 을 onSelect 로 리프팅한다.
//   종목검색은 탭이 아니라 우측 인라인 입력(ticker 형식 검증). 활성 표시는 spec.kind 로 판단.
const TABS = [
  { key: 'watchlist', label: '관심종목' },
  { key: 'macro_dashboard', label: '시장 국면' },
  { key: 'balance', label: '내 잔고' },
]

// 팝업 스펙(kind) → 패널 본문. 데이터는 각 컴포넌트가 직접 조회한다(모달일 때와 동일 재사용).
// stock_report 는 ticker 형식(6자 영숫자)이 불량이면 조회하지 않고 안내만 한다(잘못된 백엔드 조회 방지).
function RightPanelBody({ spec, onClose, sessionId, onConsult }) {
  switch (spec.kind) {
    case 'stock_report':
      if (!spec.valid) {
        return (
          <div className="popup__state">
            종목 코드를 인식하지 못했어요. 종목명이나 6자리 코드(예: 005930)로 다시 물어봐 주세요.
          </div>
        )
      }
      return (
        <PopupStockReport
          ticker={spec.args.ticker}
          stockName={spec.args.stock_name}
          sessionId={sessionId}
          onConsult={onConsult}
        />
      )
    case 'macro_dashboard':
      // 시장 국면 게이지 + 증권사 시황 리포트 요약(자체조회). 시황은 판정이 아니라 리포트 인용.
      return (
        <>
          <RegimeGauge />
          <MarketOutlookSection />
        </>
      )
    case 'watchlist':
      return <PopupWatchlist args={spec.args} />
    case 'manage_watchlist':
      // 챗봇 자연어 편집 — 사용자가 [확인]을 눌러야 실제 반영(confirm-before-write, IMP-08).
      return <ManageWatchlistConfirm args={spec.args} valid={spec.valid} onClose={onClose} />
    case 'balance':
      // 계좌 잔고·평가액·수익현황 — /api/balance 자체조회(무파라미터·조회전용·무캐시). show_balance 툴/탭 공통.
      return <BalancePanel />
    default:
      return null
  }
}

// 종목검색 인라인 폼 — 툴바 우측 상시 노출(브라우저 prompt 금지). 유효 ticker 만 onSubmit.
// 형식 불량(6자 영숫자 아님)이면 조회하지 않고(잘못된 백엔드 조회 방지) 짧은 안내를 띄운다 —
//   안내 색은 뉴트럴 회색(--c-text-secondary) — 빨강은 위험(손실·패닉) 전용이라 폼 힌트엔 쓰지 않는다.
function TickerSearch({ onSubmit }) {
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')
  function submit(e) {
    e.preventDefault()
    const t = draft.trim()
    if (!isValidTicker(t)) {
      // ticker.js SSOT — 불량이면 조회 없이 안내만(onSubmit 미호출). 잘못된 백엔드 조회 방지.
      setError('종목코드는 숫자·영문 6자리입니다 (예: 005930).')
      return
    }
    setError('')
    onSubmit(t)
    setDraft('')
  }
  return (
    <form className="right-panel__search" onSubmit={submit} autoComplete="off">
      <div className="right-panel__search-row">
        <input
          className="right-panel__search-input"
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value)
            if (error) setError('') // 다시 타이핑하면 안내 해제(자기치유)
          }}
          placeholder="종목코드 6자리(예: 005930)"
          aria-label="종목코드 입력"
          aria-invalid={error ? 'true' : undefined}
        />
        <button type="submit" className="refresh right-panel__search-go" disabled={!draft.trim()}>
          조회
        </button>
      </div>
      {error ? (
        <p className="right-panel__search-hint" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  )
}

// 패널 전환 스켈레톤 — kind 전환 시 짧게(450ms) shimmer 로 로딩감을 준다(초기 마운트는 즉시 본문).
function PanelSkeleton() {
  return (
    <div className="right-panel__skeleton" aria-label="불러오는 중" aria-busy="true">
      <div className="skeleton right-panel__skel-title" />
      <div className="skeleton right-panel__skel-row" />
      <div className="skeleton right-panel__skel-row" />
      <div className="skeleton right-panel__skel-row" />
      <div className="skeleton right-panel__skel-block" />
    </div>
  )
}

// 전환 스켈레톤 지속(ms) — 짧은 로딩감(실데이터는 각 본문 컴포넌트가 별도 조회).
const PANEL_SKELETON_MS = 450

export default function RightPanel({ spec, onSelect, onClose, sessionId, onConsult }) {
  const activeKind = spec?.kind ?? null

  // 전환 스켈레톤: kind(또는 종목) 변화 시 잠깐 shimmer. 초기 마운트는 건너뛴다(첫 화면 지연·테스트 방해 방지).
  const [loading, setLoading] = useState(false)
  const firstRef = useRef(true)
  useEffect(() => {
    if (firstRef.current) {
      firstRef.current = false
      return
    }
    setLoading(true)
    const id = setTimeout(() => setLoading(false), PANEL_SKELETON_MS)
    return () => clearTimeout(id)
  }, [activeKind, spec?.args?.ticker])

  function select(kind) {
    onSelect({ kind, args: {}, valid: true })
  }

  const title = spec
    ? spec.kind === 'stock_report' && spec.valid && spec.args?.stock_name
      ? `${spec.args.stock_name} · ${PANEL_TITLE.stock_report}`
      : PANEL_TITLE[spec.kind] ?? '패널'
    : null

  return (
    <section className="right-panel" aria-label="동적 패널">
      {/* ── 툴바: 세그먼트 탭(관심종목/시장 국면/내 잔고) + 우측 인라인 종목검색 ── */}
      <div className="right-panel__toolbar" role="toolbar" aria-label="빠른 탐색">
        <div className="right-panel__tabs">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              className="right-panel__tab"
              aria-pressed={activeKind === t.key}
              onClick={() => select(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <TickerSearch
          onSubmit={(ticker) => onSelect({ kind: 'stock_report', args: { ticker }, valid: true })}
        />
      </div>

      {/* ── 본문: spec.kind → 인라인 컴포넌트(전환 시 스켈레톤). 빈 상태는 탭으로 탐색 유도(에러 화면 아님) ── */}
      {spec ? (
        <>
          <header className="right-panel__head">
            <h2 className="right-panel__title">{title}</h2>
            <button
              type="button"
              className="right-panel__close"
              onClick={onClose}
              aria-label="패널 닫기"
            >
              ✕
            </button>
          </header>
          <div className="right-panel__body">
            {loading ? (
              <PanelSkeleton />
            ) : (
              <RightPanelBody
                spec={spec}
                onClose={onClose}
                sessionId={sessionId}
                onConsult={onConsult}
              />
            )}
          </div>
        </>
      ) : (
        <div className="right-panel__empty">
          위 탭으로 국면·관심종목·잔고를 살펴보거나, 좌측 채팅으로 물어보세요.
        </div>
      )}
    </section>
  )
}
