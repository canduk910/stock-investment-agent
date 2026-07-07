import { useEffect, useRef, useState } from 'react'
import { fetchStockBundle, searchStocks } from '../api.js'
import { sampleBundle } from '../fixtures/sampleBundle.js'
import StockReportView from './StockReportView.jsx'

// 종목 리포트 컨테이너 — 종목명/코드 자동완성 검색 + 번들 1회 조회 → StockReportView 렌더.
// 팝업 데이터는 LLM 이 아니라 프론트가 직접 조회한다(환각 차단 + 최신성, frontend-engineer 원칙2).
// 자동완성은 /api/stocks/search(KIS 마스터 전 종목). 선택 시 코드로 조회. 팝업/챗 라우팅은 W09.
//
// dev 폴백: 백엔드 미연결(네트워크/HTTP 오류)이면 샘플 fixture 로 폴백하고 배너로 명시한다.
export default function StockReport() {
  const [input, setInput] = useState('005930')
  const [bundle, setBundle] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [usingSample, setUsingSample] = useState(false)

  // 자동완성 상태
  const [suggestions, setSuggestions] = useState([])
  const [open, setOpen] = useState(false)
  const [activeIdx, setActiveIdx] = useState(-1)
  const skipSearchRef = useRef(false) // 선택 직후 재검색 방지
  const boxRef = useRef(null)

  async function load(ticker) {
    setLoading(true)
    setError(null)
    setOpen(false)
    try {
      // 섹션 실패(partial_failure)는 정상 200 응답이라 그대로 렌더(전체 에러 화면 금지).
      const b = await fetchStockBundle(ticker)
      setBundle(b)
      setUsingSample(false)
    } catch (e) {
      // 네트워크/HTTP 오류 = 백엔드 미연결(dev). 샘플로 폴백하되 명시.
      setBundle({ ...sampleBundle, ticker })
      setUsingSample(true)
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  // 최초 진입 시 기본 티커로 로드(백엔드 있으면 실데이터, 없으면 샘플) → 리포트가 항상 보인다.
  useEffect(() => {
    load('005930')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 디바운스 자동완성 검색(180ms). 선택 직후 1회는 건너뛴다.
  useEffect(() => {
    if (skipSearchRef.current) {
      skipSearchRef.current = false
      return
    }
    const q = input.trim()
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
  }, [input])

  // 바깥 클릭 시 드롭다운 닫기.
  useEffect(() => {
    function onDocMouseDown(e) {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocMouseDown)
    return () => document.removeEventListener('mousedown', onDocMouseDown)
  }, [])

  function selectStock(s) {
    skipSearchRef.current = true
    setInput(s.ticker) // 필드엔 코드(명확) — 종목명은 리포트 헤더에 표시됨
    setSuggestions([])
    setOpen(false)
    load(s.ticker)
  }

  function onSubmit(e) {
    e.preventDefault()
    const q = input.trim()
    if (!q) return
    if (open && activeIdx >= 0 && suggestions[activeIdx]) {
      selectStock(suggestions[activeIdx])
    } else if (/^[0-9A-Za-z]{6}$/.test(q)) {
      setOpen(false)
      load(q) // 6자리 코드 직접 입력
    } else if (suggestions.length) {
      selectStock(suggestions[0]) // 이름 입력 → 첫 후보
    } else {
      load(q)
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
    <section className="dashboard report-page">
      <header className="dashboard__header">
        <div>
          <h1>종목 종합리포트</h1>
          <p className="dashboard__subtitle">
            종목명·코드 검색 · 번들 1회 조회 · 정량 요약은 코드 확정(LLM 미개입)
          </p>
        </div>
        <form className="ticker-form" onSubmit={onSubmit} autoComplete="off">
          <div className="ticker-form__box" ref={boxRef}>
            <input
              className="ticker-form__input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              onFocus={() => suggestions.length > 0 && setOpen(true)}
              placeholder="종목명 또는 코드 (예: 삼성전자, 005930)"
              aria-label="종목 검색"
              role="combobox"
              aria-expanded={open}
              aria-autocomplete="list"
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
                      selectStock(s)
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
          <button className="refresh" type="submit" disabled={loading}>
            {loading ? '조회 중…' : '조회'}
          </button>
        </form>
      </header>

      {usingSample && (
        <div className="banner banner--warn" role="status">
          백엔드 미연결({error}) — <strong>샘플 데이터</strong>를 표시합니다. 통합 시 실데이터로
          대체됩니다.
          <button className="banner__retry" onClick={() => load(bundle?.ticker ?? '005930')}>
            ↻ 재시도
          </button>
        </div>
      )}

      {bundle ? (
        <StockReportView bundle={bundle} />
      ) : (
        <div className="report__empty">종목명 또는 코드로 조회하세요.</div>
      )}
    </section>
  )
}
