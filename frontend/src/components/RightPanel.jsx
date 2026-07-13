import { useEffect, useRef, useState } from 'react'
import { isValidTicker } from '../lib/ticker.js'
import { searchStocks } from '../api.js'
import PopupStockReport from './PopupStockReport.jsx'
import PopupWatchlist from './PopupWatchlist.jsx'
import ManageWatchlistConfirm from './ManageWatchlistConfirm.jsx'
import RegimeGauge from './RegimeGauge.jsx'
import MarketOutlookSection from './MarketOutlookSection.jsx'
import BalancePanel from './BalancePanel.jsx'
import KisSettingsPanel from './KisSettingsPanel.jsx'

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
  settings: '설정 · KIS API 키',
}

// 세그먼트 탭(SSOT) — 대화 없이 직접 탐색. 클릭 시 해당 kind spec 을 onSelect 로 리프팅한다.
//   종목검색은 탭이 아니라 우측 인라인 입력(ticker 형식 검증). 활성 표시는 spec.kind 로 판단.
const TABS = [
  { key: 'watchlist', label: '관심종목' },
  { key: 'macro_dashboard', label: '시장 국면' },
  { key: 'balance', label: '내 잔고' },
  { key: 'settings', label: '설정' },
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
    case 'settings':
      // 유저별 KIS API 키 등록/상태/삭제 — 탭 전용(챗 팝업 아님). 시크릿은 서버로만·마스킹 상태만.
      return <KisSettingsPanel />
    default:
      return null
  }
}

// 종목검색 인라인 폼 — 툴바 우측 상시 노출(브라우저 prompt 금지). **종목명 자동완성 원복(항목6)**:
//   종목명/코드 입력 → KIS 마스터 검색(/api/stocks/search, StockReport.jsx 패턴) → 후보 드롭다운 →
//   선택 시 유효 ticker 로 onSubmit(ticker, 종목명). 코드 직접입력은 isValidTicker(ticker.js SSOT).
//   후보 없는 이름·부분입력은 조회하지 않고(잘못된 백엔드 조회 방지) 짧은 안내만 —
//   안내 색은 뉴트럴 회색(--c-text-secondary), 검색 실패는 조용히(코드 직접입력 경로 보존).
function TickerSearch({ onSubmit }) {
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [open, setOpen] = useState(false)
  const [activeIdx, setActiveIdx] = useState(-1)
  const skipSearchRef = useRef(false) // 선택 직후 1회 재검색 방지
  const boxRef = useRef(null)

  // 디바운스 자동완성 검색(180ms). 검색 실패는 조용히(코드 직접입력 경로 보존).
  useEffect(() => {
    if (skipSearchRef.current) {
      skipSearchRef.current = false
      return
    }
    const q = draft.trim()
    if (!q) {
      setSuggestions([])
      setOpen(false)
      return
    }
    const timer = setTimeout(async () => {
      try {
        const results = await searchStocks(q, 8)
        setSuggestions(results)
        setOpen(results.length > 0)
        setActiveIdx(-1)
      } catch {
        setSuggestions([]) // 검색 실패는 조용히 — 코드 직접 입력 가능
        setOpen(false)
      }
    }, 180)
    return () => clearTimeout(timer)
  }, [draft])

  // 바깥 클릭 시 드롭다운 닫기.
  useEffect(() => {
    function onDocMouseDown(e) {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocMouseDown)
    return () => document.removeEventListener('mousedown', onDocMouseDown)
  }, [])

  function pick(stock) {
    skipSearchRef.current = true
    setDraft('')
    setSuggestions([])
    setOpen(false)
    setError('')
    onSubmit(stock.ticker, stock.name) // 후보는 유효 ticker 확정 + 종목명(패널 제목용)
  }

  function submit(e) {
    e.preventDefault()
    const t = draft.trim()
    if (open && activeIdx >= 0 && suggestions[activeIdx]) {
      pick(suggestions[activeIdx]) // 키보드/활성 후보 확정
    } else if (isValidTicker(t)) {
      setError('')
      onSubmit(t) // 6자 코드 직접 조회(ticker.js SSOT — 팝업 라우팅과 동일 규칙)
      setDraft('')
      setOpen(false)
    } else if (suggestions.length) {
      pick(suggestions[0]) // 이름 입력 → 첫 후보
    } else {
      // 이름·부분입력인데 후보 없음 → 조회 없이 안내만(잘못된 백엔드 조회 방지).
      setError('종목명 또는 코드(6자리)로 검색하세요 (예: 삼성전자, 005930).')
    }
  }

  function onKeyDown(e) {
    if (!open || !suggestions.length) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIdx((i) => Math.min(i + 1, suggestions.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <form className="right-panel__search" onSubmit={submit} autoComplete="off">
      <div className="right-panel__search-row">
        <div className="right-panel__search-box" ref={boxRef}>
          <input
            className="right-panel__search-input"
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value)
              if (error) setError('') // 다시 타이핑하면 안내 해제(자기치유)
            }}
            onKeyDown={onKeyDown}
            onFocus={() => suggestions.length > 0 && setOpen(true)}
            placeholder="종목명 또는 코드 (예: 삼성전자, 005930)"
            aria-label="종목 검색"
            role="combobox"
            aria-expanded={open}
            aria-autocomplete="list"
            aria-invalid={error ? 'true' : undefined}
          />
          {open && (
            <ul className="autocomplete" role="listbox" aria-label="종목 검색 결과">
              {suggestions.map((s, i) => (
                <li
                  key={s.ticker}
                  role="option"
                  aria-selected={i === activeIdx}
                  className={`autocomplete__item ${i === activeIdx ? 'is-active' : ''}`}
                  onMouseDown={(e) => {
                    e.preventDefault() // input blur 로 닫히기 전에 선택
                    pick(s)
                  }}
                  onMouseEnter={() => setActiveIdx(i)}
                >
                  <span className="autocomplete__name">{s.name}</span>
                  <span className="autocomplete__meta">
                    {s.ticker} · {s.market}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
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
          onSubmit={(ticker, stockName) =>
            onSelect({
              kind: 'stock_report',
              args: stockName ? { ticker, stock_name: stockName } : { ticker },
              valid: true,
            })
          }
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
