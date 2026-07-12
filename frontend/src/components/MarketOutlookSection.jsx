import { useEffect, useState } from 'react'
import { fetchMarketOutlook, fetchNaverMarketOutlook } from '../api.js'

// 시장 국면 페이지(RegimeGauge 아래) — 증권사 '시황(market outlook) 리포트' 요약 카드.
// 실데이터는 프론트가 fetchMarketOutlook 로 직접 조회한다(환각 차단). 각 요약은 **해당 증권사 시황
// 리포트의 내용 인용**이지 에이전트의 시장 판정이 아니다(시장 국면 판정은 코드/매크로 엔진). 출처 귀속·면책.
// 색은 theme.css 토큰만. 애널리스트 카드 CSS(.analyst*)를 재사용한다.

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

function OutlookCard({ report }) {
  const s = report.summary ?? {}
  return (
    <article className="analyst__card">
      <header className="analyst__card-head">
        <div className="analyst__meta">
          <span className="analyst__broker">{s.증권사 || report.broker || '증권사'}</span>
          {report.date ? <span className="analyst__date">{report.date}</span> : null}
        </div>
        {s.시장전망 ? (
          <span className="chip analyst__chip-opinion" title="리포트가 밝힌 시장 전망(출처 귀속)">
            시장전망 · {s.시장전망}
          </span>
        ) : null}
      </header>

      {(s.제목 || report.title) ? (
        <p className="analyst__title">{s.제목 || report.title}</p>
      ) : null}
      {s.요약 ? <p className="analyst__summary">“{s.요약}”</p> : null}

      <BulletList label="핵심요지" items={s.핵심요지} />
      <BulletList label="리스크요인" items={s.리스크요인} tone="risk" />

      {s.면책고지 ? <p className="analyst__fine">{s.면책고지}</p> : null}

      {report.pdf_url ? (
        <div className="analyst__actions">
          <a
            className="analyst__pdf"
            href={report.pdf_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            원문 PDF ↗
          </a>
        </div>
      ) : null}
    </article>
  )
}

export default function MarketOutlookSection() {
  const [reports, setReports] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [fetching, setFetching] = useState(false)
  const [fetchMsg, setFetchMsg] = useState(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchMarketOutlook()
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
  }, [])

  async function fetchNaver() {
    setFetching(true)
    setFetchMsg(null)
    try {
      const res = await fetchNaverMarketOutlook(15)
      setFetchMsg(
        `네이버 최신 시황 ${res.fetched}건 확인 · 새 요약 ${res.new}건` +
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
    <section className="analyst" aria-label="시황 리포트 요약">
      <div className="analyst__head">
        <h3 className="report__section-label">증권사 시황 리포트 요약</h3>
        <button type="button" className="refresh analyst__fetch" onClick={fetchNaver} disabled={fetching}>
          {fetching ? '가져오는 중…' : '네이버 최신 시황 가져오기'}
        </button>
      </div>

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
          <div className="analyst__cards">
            {reports.map((r) => (
              <OutlookCard key={r.report_id} report={r} />
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
    </section>
  )
}
