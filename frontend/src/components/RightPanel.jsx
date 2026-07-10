import { useState } from 'react'
import { isValidTicker } from '../lib/ticker.js'
import PopupStockReport from './PopupStockReport.jsx'
import PopupWatchlist from './PopupWatchlist.jsx'
import ManageWatchlistConfirm from './ManageWatchlistConfirm.jsx'
import RegimeGauge from './RegimeGauge.jsx'
import BalancePanel from './BalancePanel.jsx'

// 우측 동적 패널(UX 개편) — 좌측 상시 채팅 옆에서 맥락형 콘텐츠를 인라인 렌더한다(모달 폐기).
// 두 경로로 구동: (a) 챗봇 tool_call(App 이 onShowPanel 로 spec 리프팅) · (b) 상단 퀵버튼(대화 없이 직접 탐색).
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

// 퀵버튼 정의(SSOT) — 대화 없이 직접 탐색. 클릭 시 해당 kind spec 을 onSelect 로 리프팅한다.
//   종목검색은 kind 가 없다(ticker 입력 폼을 펼친다). 활성 표시는 spec.kind 로 판단.
const QUICK_BUTTONS = [
  { key: 'macro_dashboard', label: '국면' },
  { key: 'watchlist', label: '관심종목' },
  { key: 'balance', label: '잔고' },
]

// 팝업 스펙(kind) → 패널 본문. 데이터는 각 컴포넌트가 직접 조회한다(모달일 때와 동일 재사용).
// stock_report 는 ticker 형식(6자 영숫자)이 불량이면 조회하지 않고 안내만 한다(잘못된 백엔드 조회 방지).
function RightPanelBody({ spec, onClose }) {
  switch (spec.kind) {
    case 'stock_report':
      if (!spec.valid) {
        return (
          <div className="popup__state">
            종목 코드를 인식하지 못했어요. 종목명이나 6자리 코드(예: 005930)로 다시 물어봐 주세요.
          </div>
        )
      }
      return <PopupStockReport ticker={spec.args.ticker} stockName={spec.args.stock_name} />
    case 'macro_dashboard':
      return <RegimeGauge />
    case 'watchlist':
      return <PopupWatchlist args={spec.args} />
    case 'manage_watchlist':
      // 챗봇 자연어 편집 — 사용자가 [확인]을 눌러야 실제 반영(confirm-before-write, IMP-08).
      return <ManageWatchlistConfirm args={spec.args} valid={spec.valid} onClose={onClose} />
    case 'balance':
      // 계좌 잔고·평가액·수익현황 — /api/balance 자체조회(무파라미터·조회전용·무캐시). show_balance 툴/퀵버튼 공통.
      return <BalancePanel />
    default:
      return null
  }
}

// 종목검색 인라인 폼 — 브라우저 prompt 금지(WatchlistView 와 동일 원칙). 유효 ticker 만 onSelect.
// 형식 불량(6자 영숫자 아님)이면 조회하지 않고(잘못된 백엔드 조회 방지) 짧은 안내를 띄운다 —
//   "조회만 조용히 무시"는 사용자가 왜 안 되는지 몰라 혼란스러웠다(UX 개선). 안내 색은 뉴트럴
//   회색(--c-text-secondary) — 빨강은 위험(손실·패닉) 전용이라 폼 힌트엔 쓰지 않는다.
function TickerSearch({ onSubmit }) {
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')
  function submit(e) {
    e.preventDefault()
    const t = draft.trim()
    if (!isValidTicker(t)) {
      // ticker.js SSOT — 불량이면 조회 없이 안내만(onSelect 미호출). 잘못된 백엔드 조회 방지.
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

export default function RightPanel({ spec, onSelect, onClose }) {
  // 종목검색 폼 펼침 상태(퀵버튼과 병렬). 다른 퀵버튼을 누르면 접는다(한 번에 하나만 강조).
  const [searching, setSearching] = useState(false)
  const activeKind = spec?.kind ?? null

  function select(kind) {
    setSearching(false)
    onSelect({ kind, args: {}, valid: true })
  }

  const title = spec
    ? spec.kind === 'stock_report' && spec.valid && spec.args?.stock_name
      ? `${spec.args.stock_name} · ${PANEL_TITLE.stock_report}`
      : PANEL_TITLE[spec.kind] ?? '패널'
    : null

  return (
    <section className="right-panel" aria-label="동적 패널">
      {/* ── 퀵버튼 툴바: 대화 없이 국면/관심종목/잔고/종목검색 직접 탐색 ── */}
      <div className="right-panel__toolbar" role="toolbar" aria-label="빠른 탐색">
        {QUICK_BUTTONS.map((b) => (
          <button
            key={b.key}
            type="button"
            className="right-panel__quick"
            aria-pressed={activeKind === b.key}
            onClick={() => select(b.key)}
          >
            {b.label}
          </button>
        ))}
        <button
          type="button"
          className="right-panel__quick"
          aria-pressed={searching}
          onClick={() => setSearching((s) => !s)}
        >
          종목검색
        </button>
      </div>

      {searching ? (
        <TickerSearch
          onSubmit={(ticker) => {
            setSearching(false)
            onSelect({ kind: 'stock_report', args: { ticker }, valid: true })
          }}
        />
      ) : null}

      {/* ── 본문: spec.kind → 인라인 컴포넌트. 빈 상태는 퀵버튼으로 탐색 유도(에러 화면 아님) ── */}
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
            <RightPanelBody spec={spec} onClose={onClose} />
          </div>
        </>
      ) : (
        <div className="right-panel__empty">
          위 버튼으로 국면·관심종목·잔고를 살펴보거나, 좌측 채팅으로 물어보세요.
        </div>
      )}
    </section>
  )
}
