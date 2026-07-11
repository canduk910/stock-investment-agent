import { useEffect, useState } from 'react'
import { fetchAnalystReports, fetchNaverReports, setReportContext } from '../api.js'

// 종목 상세(StockReportView) 하단 — 그 ticker 의 네이버 애널리스트 리포트 '요약' 카드 섹션.
// 실데이터(요약)는 프론트가 fetchAnalystReports 로 직접 조회한다(환각 차단) — LLM 응답에서 꺼내지 않는다.
// 각 요약은 **해당 증권사 리포트의 내용 인용**이지 에이전트 자체 매수/매도 판정이 아니다(출처 귀속·면책 상시).
// "이 리포트로 상담하기" → setReportContext 로 세션 상담 컨텍스트를 핀 고정 → 좌측 챗이 그 리포트를
//   근거로 후속 자문(App 이 배너 표시). 색은 theme.css 토큰만(상담 CTA=주황 강조).

const CONSULT_DISCLAIMER =
  '아래 요약은 각 증권사 애널리스트 리포트의 내용이며, 본 서비스의 투자 판단·매매 권유가 아닙니다. ' +
  '목표주가·투자의견은 리포트가 밝힌 값이고, 참고용입니다(면허 있는 투자자문 아님).'

// 리스트(핵심요지/리스크요인) 렌더 — 비면 생략. 원소 문자열 그대로(출처 리포트 문구).
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

function ReportCard({ report, ticker, sessionId, onConsult }) {
  const s = report.summary ?? {}
  const [consulting, setConsulting] = useState(false)
  const [consulted, setConsulted] = useState(false)
  const [err, setErr] = useState(null)

  async function consult() {
    if (!sessionId) {
      setErr('상담 세션이 없어 컨텍스트를 불러올 수 없습니다.')
      return
    }
    setConsulting(true)
    setErr(null)
    try {
      const res = await setReportContext(sessionId, ticker, report.report_id)
      setConsulted(true)
      onConsult?.(res.broker || s.증권사 || report.broker || '')
    } catch (e) {
      setErr(`상담 컨텍스트를 불러오지 못했습니다(${e.message}).`)
    } finally {
      setConsulting(false)
    }
  }

  return (
    <article className="analyst__card">
      <header className="analyst__card-head">
        <div className="analyst__meta">
          <span className="analyst__broker">{s.증권사 || report.broker || '증권사'}</span>
          {report.date ? <span className="analyst__date">{report.date}</span> : null}
        </div>
        <div className="analyst__opinion">
          {s.목표주가 ? (
            <span className="chip chip--navy">목표주가 {s.목표주가}</span>
          ) : null}
          {s.투자의견 ? (
            <span className="chip analyst__chip-opinion" title="리포트가 밝힌 투자의견(출처 귀속)">
              리포트 의견 · {s.투자의견}
            </span>
          ) : null}
        </div>
      </header>

      {report.title ? <p className="analyst__title">{report.title}</p> : null}
      {s.요약 ? <p className="analyst__summary">“{s.요약}”</p> : null}

      <BulletList label="핵심요지" items={s.핵심요지} />
      <BulletList label="리스크요인" items={s.리스크요인} tone="risk" />

      {s.면책고지 ? <p className="analyst__fine">{s.면책고지}</p> : null}

      <div className="analyst__actions">
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
        <button
          type="button"
          className="analyst__consult"
          onClick={consult}
          disabled={consulting || consulted || !sessionId}
        >
          {consulted ? '✓ 상담 컨텍스트로 불러옴' : consulting ? '불러오는 중…' : '이 리포트로 상담하기'}
        </button>
      </div>
      {err ? (
        <p className="analyst__err" role="alert">
          {err}
        </p>
      ) : null}
    </article>
  )
}

export default function AnalystReportsSection({ ticker, sessionId, onConsult }) {
  const [reports, setReports] = useState(null) // null=미로딩, []=없음
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [fetching, setFetching] = useState(false) // 네이버 수집 진행
  const [fetchMsg, setFetchMsg] = useState(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchAnalystReports(ticker)
      setReports(data.reports ?? [])
    } catch (e) {
      setError(e.message)
      setReports(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker])

  // 네이버 최신 리포트 수집(서버) → 완료 후 이 종목 요약 재조회. 결과 카운트 안내.
  async function fetchNaver() {
    setFetching(true)
    setFetchMsg(null)
    try {
      const res = await fetchNaverReports(30)
      setFetchMsg(
        `네이버 최신 리포트 ${res.fetched}건 확인 · 새 요약 ${res.new}건` +
          (res.failed ? ` · 실패 ${res.failed}건` : ''),
      )
      await load()
    } catch (e) {
      setFetchMsg(`수집 실패(${e.message}).`)
    } finally {
      setFetching(false)
    }
  }

  return (
    <section className="analyst" aria-label="애널리스트 리포트 요약">
      <div className="analyst__head">
        <h3 className="report__section-label">증권사 애널리스트 리포트 요약</h3>
        <button
          type="button"
          className="refresh analyst__fetch"
          onClick={fetchNaver}
          disabled={fetching}
        >
          {fetching ? '가져오는 중…' : '네이버 최신 리포트 가져오기'}
        </button>
      </div>

      {fetchMsg ? (
        <p className="analyst__fetchmsg" role="status">
          {fetchMsg}
        </p>
      ) : null}

      {loading ? (
        <div className="popup__state">애널리스트 리포트 조회 중…</div>
      ) : error ? (
        <div className="popup__state">
          <span>리포트 조회 실패: {error}</span>
          <button type="button" className="refresh" onClick={load}>
            ↻ 재시도
          </button>
        </div>
      ) : reports && reports.length > 0 ? (
        <>
          <div className="analyst__cards">
            {reports.map((r) => (
              <ReportCard
                key={r.report_id}
                report={r}
                ticker={ticker}
                sessionId={sessionId}
                onConsult={onConsult}
              />
            ))}
          </div>
          <p className="analyst__disclaimer" role="note">
            {CONSULT_DISCLAIMER}
          </p>
        </>
      ) : (
        <div className="analyst__empty">
          아직 저장된 애널리스트 리포트가 없어요. 위 버튼으로 네이버 최신 리포트를 가져오면
          이 종목의 요약이 있을 때 여기에 표시됩니다.
        </div>
      )}
    </section>
  )
}
