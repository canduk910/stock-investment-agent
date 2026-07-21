import { useEffect, useRef, useState } from 'react'
import { setMarketOutlookContext } from '../api.js'
import { groupReportsByDate, threeLineSummary } from '../lib/marketOutlook.js'
import FetchProgress from './FetchProgress.jsx'

// 증권사 '시황(market outlook) 리포트' 요약 카드 뷰 — **controlled**(reports·수집상태를 상위 MacroDashboard
// 가 소유·주입). 각 요약은 **해당 증권사 시황 리포트의 내용 인용**이지 에이전트의 시장 판정이 아니다
// (시장 국면 판정은 코드/매크로 엔진). 출처 귀속·면책. 색은 theme.css 토큰만(시장전망 칩=중립 톤).
//
// UX(항목4): 작성일별 구분 → 컴팩트 카드(증권사·시장전망·제목·3줄요약) → 클릭 시 상세 오버레이.
// (자체 fetch·자동 최신화·금일의 요약은 MacroDashboard 컨테이너로 이관.)

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

export default function MarketOutlookSection({
  reports,
  loading = false,
  error = null,
  fetching = false,
  progress = null,
  fetchMsg = null,
  autoNote = null,
  onFetch,
  onReload,
  sessionId,
  onConsult,
} = {}) {
  const [selected, setSelected] = useState(null) // 상세 오버레이 대상 report(null=닫힘)
  const triggerRef = useRef(null) // 오버레이 닫을 때 포커스 복원 대상

  function openDetail(report) {
    triggerRef.current = document.activeElement // 트리거(카드) 기억
    setSelected(report)
  }

  function closeDetail() {
    setSelected(null)
    triggerRef.current?.focus?.() // 포커스 복원(접근성)
  }

  const groups = groupReportsByDate(reports ?? [])

  return (
    <section className="analyst" aria-label="시황 리포트 요약">
      <div className="analyst__head">
        <h3 className="report__section-label">증권사 시황 리포트 요약</h3>
        <button type="button" className="refresh analyst__fetch" onClick={onFetch} disabled={fetching}>
          {fetching ? '가져오는 중…' : '네이버 최신 시황 가져오기'}
        </button>
      </div>

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
          <button type="button" className="refresh" onClick={onReload}>
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
