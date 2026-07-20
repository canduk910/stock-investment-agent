import { useEffect, useRef, useState } from 'react'
import {
  fetchMarketOutlook,
  fetchNaverMarketOutlook,
  streamFetchMarketOutlook,
  setMarketOutlookContext,
  fetchMarketOutlookSummary,
} from '../api.js'
import {
  groupReportsByDate,
  threeLineSummary,
  isOutlookStale,
  todayStampKST,
} from '../lib/marketOutlook.js'
import FetchProgress, { applyProgressEvent } from './FetchProgress.jsx'

// 자동 최신화 중복 방지 가드 — 날짜별 최대 1회 자동수집(패널 반복 오픈·주말 무자료 시 폭주 방지).
const AUTO_FETCH_KEY = 'mo_autofetch_date'

// 시장 국면 페이지(RegimeGauge 아래) — 증권사 '시황(market outlook) 리포트' 요약.
// 실데이터는 프론트가 fetchMarketOutlook 로 직접 조회한다(환각 차단). 각 요약은 **해당 증권사 시황
// 리포트의 내용 인용**이지 에이전트의 시장 판정이 아니다(시장 국면 판정은 코드/매크로 엔진). 출처 귀속·면책.
// 색은 theme.css 토큰만. 시장전망 칩은 중립 톤(가격방향색 아님).
//
// UX(항목4): 작성일별 구분 → 컴팩트 카드(증권사·시장전망·제목·3줄요약) → 클릭 시 상세 오버레이.

const DISCLAIMER =
  '아래 요약은 각 증권사 시황 리포트의 내용이며, 본 서비스의 시장 판정·매매 권유가 아닙니다. ' +
  '시장 국면 판정은 코드(매크로 엔진)가 하며, 시황 요약은 참고용입니다(면허 있는 투자자문 아님).'

function BulletList({ label, items, tone }) {
  if (!items || items.length === 0) return null
  return (
    <div className="analyst__list">
      <span className="analyst__list-label">{label}</span>
      <ul className={`analyst__bullets${tone ? ` analyst__bullets--${tone}` : ''}`}>
        {items.map((it, i) => (
          <li key={i}>{it}</li>
        ))}
      </ul>
    </div>
  )
}

// 컴팩트 카드 — 증권사·시장전망 칩·제목·3줄요약. 카드 전체가 버튼(클릭·키보드 → 상세 오버레이).
function OutlookCard({ report, onOpen }) {
  const s = report.summary ?? {}
  const three = threeLineSummary(s)
  return (
    <button type="button" className="mo-card" onClick={() => onOpen(report)}>
      <div className="mo-card__head">
        <span className="mo-card__broker">{s.증권사 || report.broker || '증권사'}</span>
        {s.시장전망 ? (
          <span className="chip mo-card__stance" title="리포트가 밝힌 시장 전망(출처 귀속)">
            시장전망 · {s.시장전망}
          </span>
        ) : null}
      </div>
      {(s.제목 || report.title) ? (
        <p className="mo-card__title">{s.제목 || report.title}</p>
      ) : null}
      {three.length > 0 ? (
        <ul className="mo-card__three">
          {three.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      ) : (
        <p className="mo-card__three-empty">요약 준비 중</p>
      )}
      <span className="mo-card__more" aria-hidden="true">자세히 ▸</span>
    </button>
  )
}

// 상세 오버레이 — 딤 배경 + 중앙 카드. 이 프로젝트는 범용 Modal.jsx 를 폐기했으나, 시황 상세
// '클릭 팝업'(사용자 결정)에 한해 접근성 오버레이를 도입한다(범용 모달 부활 아님, 이 뷰 전용).
// Esc·배경 클릭·✕ 로 닫힘. React DOM 오버레이(브라우저 alert/confirm 아님 — 이벤트 블로킹 없음).
function MarketOutlookDetailOverlay({ report, onClose, sessionId, onConsult }) {
  const closeRef = useRef(null)
  const [consulting, setConsulting] = useState(false)

  useEffect(() => {
    closeRef.current?.focus() // 열릴 때 닫기 버튼에 포커스(접근성)
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

  const s = report.summary ?? {}

  // 이 시황으로 상담하기 — 서버가 store 에서 요약 조회해 세션 컨텍스트 핀(요약 본문 신뢰전송 없음).
  //   성공 시 좌측 챗 상담 배너(onConsult) + 오버레이 닫아 대화로 유도. 애널리스트와 동일 메커니즘.
  async function consult() {
    if (!sessionId || consulting) return
    setConsulting(true)
    try {
      const res = await setMarketOutlookContext(sessionId, report.report_id)
      onConsult?.(res.broker || s.증권사 || report.broker || '')
      onClose()
    } catch {
      /* 실패는 graceful — 오버레이 유지 */
    } finally {
      setConsulting(false)
    }
  }
  return (
    <div className="mo-overlay" onClick={onClose}>
      <div
        className="mo-overlay__card"
        role="dialog"
        aria-modal="true"
        aria-label="시황 리포트 상세"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="mo-overlay__head">
          <div className="mo-overlay__meta">
            <span className="mo-card__broker">{s.증권사 || report.broker || '증권사'}</span>
            {report.date ? <span className="analyst__date">{report.date}</span> : null}
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

        {s.시장전망 ? (
          <span className="chip mo-card__stance" title="리포트가 밝힌 시장 전망(출처 귀속)">
            시장전망 · {s.시장전망}
          </span>
        ) : null}
        {(s.제목 || report.title) ? (
          <p className="mo-overlay__title">{s.제목 || report.title}</p>
        ) : null}
        {s.요약 ? <p className="analyst__summary">“{s.요약}”</p> : null}

        <BulletList label="핵심요지" items={s.핵심요지} />
        <BulletList label="리스크요인" items={s.리스크요인} tone="risk" />

        {s.면책고지 ? <p className="analyst__fine">{s.면책고지}</p> : null}

        <div className="analyst__actions">
          {onConsult ? (
            <button
              type="button"
              className="analyst__consult"
              onClick={consult}
              disabled={consulting || !sessionId}
              title={sessionId ? '이 시황 리포트로 이어서 상담' : '대화 준비 후 이용 가능'}
            >
              {consulting ? '컨텍스트 설정 중…' : '이 시황으로 상담하기'}
            </button>
          ) : null}
          {report.pdf_url ? (
            <a
              className="analyst__pdf"
              href={report.pdf_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              원문 PDF ↗
            </a>
          ) : null}
        </div>
      </div>
    </div>
  )
}

// 금일의 요약 — 최근 5개 시황 리포트를 종합·중복제거해 10줄 핵심메시지로(온디맨드). 애널리스트
// 종합요약(CombinedSummary) 패턴. 시각 강조 카드(주황 강조 소프트·📌). 종합=여러 리포트 인용·면책.
function DailySummary() {
  const [state, setState] = useState('idle') // idle | loading | done | error
  const [data, setData] = useState(null)
  const [errMsg, setErrMsg] = useState(null)

  async function generate() {
    setState('loading')
    setErrMsg(null)
    try {
      const res = await fetchMarketOutlookSummary()
      if (res.validation_failed || !res.summary) {
        setState('error')
        setErrMsg(res.message || '금일의 요약을 생성하지 못했습니다.')
      } else {
        setData(res)
        setState('done')
      }
    } catch (e) {
      setState('error')
      setErrMsg(`금일의 요약 생성 실패(${e.message}).`)
    }
  }

  const s = data?.summary ?? {}
  return (
    <div className="daily-summary">
      <div className="daily-summary__head">
        <span className="daily-summary__title">
          <span className="daily-summary__badge" aria-hidden="true">
            📌
          </span>
          금일의 요약
          <span className="daily-summary__sub">최근 시황 종합 · 최대 10줄</span>
        </span>
        <button
          type="button"
          className="daily-summary__gen"
          onClick={generate}
          disabled={state === 'loading'}
        >
          {state === 'loading' ? '생성 중…' : state === 'done' ? '↻ 다시 생성' : '금일의 요약 생성'}
        </button>
      </div>
      {state === 'error' ? (
        <p className="analyst__err" role="alert">
          {errMsg}
        </p>
      ) : null}
      {state === 'done' && data ? (
        <div className="daily-summary__body">
          <div className="daily-summary__chips">
            {s.시장전망분포 ? (
              <span className="chip daily-summary__chip" title="리포트 시장전망 분포(출처 귀속)">
                시장전망 · {s.시장전망분포}
              </span>
            ) : null}
            <span className="chip daily-summary__chip">시황 {data.report_count}개 종합</span>
          </div>
          {Array.isArray(s.종합요약) && s.종합요약.length > 0 ? (
            <ol className="daily-summary__lines">
              {s.종합요약.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ol>
          ) : null}
          {s.면책고지 ? <p className="analyst__fine">{s.면책고지}</p> : null}
        </div>
      ) : null}
    </div>
  )
}

export default function MarketOutlookSection({ sessionId, onConsult } = {}) {
  const [reports, setReports] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [fetching, setFetching] = useState(false)
  const [fetchMsg, setFetchMsg] = useState(null)
  const [progress, setProgress] = useState(null) // SSE 진행 체크리스트
  const [selected, setSelected] = useState(null) // 상세 오버레이 대상 report(null=닫힘)
  const [autoNote, setAutoNote] = useState(null) // 자동 최신화 안내(수동과 구분)
  const triggerRef = useRef(null) // 오버레이 닫을 때 포커스 복원 대상
  const autoTriedRef = useRef(false) // 마운트당 자동수집 판정 1회(StrictMode 이중마운트 방지)

  function openDetail(report) {
    triggerRef.current = document.activeElement // 트리거(카드) 기억
    setSelected(report)
  }

  function closeDetail() {
    setSelected(null)
    triggerRef.current?.focus?.() // 포커스 복원(접근성)
  }

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchMarketOutlook()
      const list = data.reports ?? []
      setReports(list)
      return list
    } catch (e) {
      setError(e.message)
      setReports(null)
      return []
    } finally {
      setLoading(false)
    }
  }

  // 저장된 최신 시황이 오늘(KST)이 아니면 자동으로 최신 수집(기존 SSE). 날짜별 1회 가드로 폭주 방지.
  function maybeAutoFetch(list) {
    const today = todayStampKST()
    if (!isOutlookStale(list, today)) return // 이미 오늘자 최신 → 자동수집 불필요
    try {
      if (localStorage.getItem(AUTO_FETCH_KEY) === today) return // 오늘 이미 자동수집 시도함
      localStorage.setItem(AUTO_FETCH_KEY, today)
    } catch {
      /* localStorage 불가 환경 — 그래도 마운트당 1회는 진행(autoTriedRef) */
    }
    setAutoNote('오늘 최신 시황을 자동으로 확인하는 중…')
    fetchNaver()
  }

  useEffect(() => {
    ;(async () => {
      const list = await load()
      if (!autoTriedRef.current) {
        autoTriedRef.current = true
        maybeAutoFetch(list)
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 네이버 최신 시황 수집을 **SSE 진행 스트림**으로 — 목록·각 리포트 처리를 실시간 표시. 끊김은 폴백.
  async function fetchNaver() {
    setFetching(true)
    setFetchMsg(null)
    setProgress({ stage: 'list', reports: [], done: 0, total: 0 })
    let finished = false
    await streamFetchMarketOutlook({
      limit: 15,
      onEvent: (ev) => {
        if (ev.type === 'done') {
          finished = true
          setFetchMsg(`새 요약 ${ev.new}건 · 확인 ${ev.fetched}건` + (ev.failed ? ` · 실패 ${ev.failed}건` : ''))
        } else if (ev.type === 'error') {
          finished = true
          setFetchMsg(`수집 실패(${ev.message}).`)
        } else {
          setProgress((p) => applyProgressEvent(p, ev))
        }
      },
      onError: async () => {
        if (finished) return
        try {
          const res = await fetchNaverMarketOutlook(15)
          setFetchMsg(`새 요약 ${res.new}건 · 확인 ${res.fetched}건` + (res.failed ? ` · 실패 ${res.failed}건` : ''))
        } catch (e) {
          setFetchMsg(`수집 실패(${e.message}).`)
        }
      },
    })
    setProgress(null)
    await load()
    setFetching(false)
    setAutoNote(null) // 자동 최신화 안내 해제(완료 메시지 fetchMsg 로 대체)
  }

  const groups = groupReportsByDate(reports ?? [])

  return (
    <section className="analyst" aria-label="시황 리포트 요약">
      <div className="analyst__head">
        <h3 className="report__section-label">증권사 시황 리포트 요약</h3>
        <button type="button" className="refresh analyst__fetch" onClick={fetchNaver} disabled={fetching}>
          {fetching ? '가져오는 중…' : '네이버 최신 시황 가져오기'}
        </button>
      </div>

      {/* 금일의 요약 — 증권사 시황리포트 요약 바로 아래(저장 시황 있을 때만). 시각 강조 카드. */}
      {reports && reports.length > 0 ? <DailySummary /> : null}

      {autoNote ? (
        <p className="analyst__fetchmsg" role="status">
          {autoNote}
        </p>
      ) : null}

      {fetching ? <FetchProgress progress={progress} /> : null}

      {fetchMsg ? (
        <p className="analyst__fetchmsg" role="status">
          {fetchMsg}
        </p>
      ) : null}

      {loading ? (
        <div className="popup__state">시황 요약 조회 중…</div>
      ) : error ? (
        <div className="popup__state">
          <span>시황 조회 실패: {error}</span>
          <button type="button" className="refresh" onClick={load}>
            ↻ 재시도
          </button>
        </div>
      ) : reports && reports.length > 0 ? (
        <>
          <div className="mo-groups">
            {groups.map((g) => (
              <div className="mo-group" key={g.date ?? '__undated__'}>
                <div className="mo-group__date">{g.date ?? '날짜 미상'}</div>
                <div className="mo-group__cards">
                  {g.reports.map((r) => (
                    <OutlookCard key={r.report_id} report={r} onOpen={openDetail} />
                  ))}
                </div>
              </div>
            ))}
          </div>
          <p className="analyst__disclaimer" role="note">
            {DISCLAIMER}
          </p>
        </>
      ) : (
        <div className="analyst__empty">
          아직 저장된 시황 리포트가 없어요. 위 버튼으로 네이버 최신 시황을 가져오면 여기에 요약이 표시됩니다.
        </div>
      )}

      {selected ? (
        <MarketOutlookDetailOverlay
          report={selected}
          onClose={closeDetail}
          sessionId={sessionId}
          onConsult={onConsult}
        />
      ) : null}
    </section>
  )
}
