import { useCallback, useEffect, useState } from 'react'
import { generateStockReport, fetchReportHistory } from '../api.js'
import { opinionTone } from '../lib/reportFormat.js'

// AI 종합 리포트(W10 P2) — "생성" 버튼 → 구조화 리포트 렌더 + 과거 히스토리 목록.
// 원칙: LLM 은 서술만, 판정·수치는 코드(현재 화면 정량요약이 이미 확정). 리스크요인 최소 1·면책 필수는
//   백엔드 Pydantic StockReport 가 강제 — 프론트는 검증 통과분(report)만 구조화해 보여준다.
//   검증 실패(validation_failed)면 report=null → "AI 서술 생성 실패" 안내(정량요약은 화면에 이미 있음).
//   종합의견 배지: 긍정적=파랑/중립=회색/신중=주황(reportFormat.opinionTone). 매수·매도 라벨은 스키마가 배제.
//   면책 고지는 리포트 하단에 항상 노출(백엔드 report.면책고지 + 화면 자체 상시 고지가 이미 존재).

export default function AiReportPanel({ ticker }) {
  const [report, setReport] = useState(null) // 검증 통과 구조화 리포트(6필드) | null
  const [meta, setMeta] = useState(null) // {validation_failed, message, regime_at_creation, created_at}
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [history, setHistory] = useState([])
  const [historyOpen, setHistoryOpen] = useState(false)

  // 종목이 바뀌면 이전 종목의 리포트/히스토리를 비운다(오표시 방지).
  useEffect(() => {
    setReport(null)
    setMeta(null)
    setError(null)
    setHistory([])
    setHistoryOpen(false)
  }, [ticker])

  const loadHistory = useCallback(async () => {
    try {
      const res = await fetchReportHistory(ticker)
      setHistory(res.history ?? [])
    } catch {
      setHistory([]) // 히스토리 조회 실패는 조용히(주 기능은 생성)
    }
  }, [ticker])

  async function onGenerate() {
    if (!ticker) return
    setLoading(true)
    setError(null)
    try {
      const res = await generateStockReport(ticker)
      setReport(res.report ?? null) // validation_failed 면 null
      setMeta({
        validation_failed: res.validation_failed,
        message: res.message,
        regime_at_creation: res.regime_at_creation,
        created_at: res.created_at,
      })
      await loadHistory() // 생성 성공 시 히스토리 갱신(누적 확인)
    } catch (e) {
      // 네트워크/HTTP 오류만 여기(생성 자체는 항상 200이라 validation 실패는 위 정상 경로).
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function toggleHistory() {
    const next = !historyOpen
    setHistoryOpen(next)
    if (next && history.length === 0) await loadHistory()
  }

  return (
    <div className="ai-report">
      <div className="ai-report__bar">
        <button
          type="button"
          className="refresh ai-report__gen"
          onClick={onGenerate}
          disabled={loading || !ticker}
        >
          {loading ? 'AI 리포트 생성 중…' : 'AI 리포트 생성'}
        </button>
        <button type="button" className="ai-report__history-toggle" onClick={toggleHistory}>
          {historyOpen ? '과거 평가 숨기기' : '과거 평가 보기'}
        </button>
        {meta?.created_at ? (
          <span className="ai-report__ts">생성 {formatTs(meta.created_at)}</span>
        ) : null}
      </div>

      {error ? (
        <div className="banner banner--warn ai-report__error" role="status">
          AI 리포트를 생성하지 못했습니다({error}).
          <button type="button" className="banner__retry" onClick={onGenerate} disabled={loading}>
            ↻ 재시도
          </button>
        </div>
      ) : null}

      {/* 검증 실패 — report=null. 정량요약은 화면 상단에 이미 있으므로 여기선 안내만(전체 에러 아님). */}
      {meta?.validation_failed ? (
        <div className="ai-report__failed" role="note">
          {meta.message ?? 'AI 서술 생성 실패 — 위 정량 요약(코드 확정)을 참고하세요.'}
        </div>
      ) : null}

      {report ? <StructuredReport report={report} regime={meta?.regime_at_creation} /> : null}

      {!report && !meta ? (
        <p className="ai-report__hint">
          버튼을 누르면 위 정량 요약·국면을 근거로 AI가 서술 요약을 생성합니다(판정·수치는 코드가 확정,
          AI는 설명만).
        </p>
      ) : null}

      {historyOpen ? <HistoryList history={history} /> : null}
    </div>
  )
}

// 구조화 리포트 본문 — 6필드. 종합의견 배지(톤 매핑) + 리스트 + 국면정합성 + 면책고지(상시).
function StructuredReport({ report, regime }) {
  const tone = opinionTone(report.종합의견)
  const points = report.투자포인트 ?? []
  const risks = report.리스크요인 ?? []
  return (
    <div className="ai-report__body">
      <div className="ai-report__head">
        <span className={`badge badge--${tone} ai-report__opinion`}>{report.종합의견}</span>
        {regime ? <span className="ai-report__regime">생성 시점 국면 · {regime}</span> : null}
      </div>

      {report.요약 ? <p className="ai-report__summary">{report.요약}</p> : null}

      {points.length > 0 ? (
        <div className="ai-report__block">
          <h4 className="ai-report__block-title">투자 포인트</h4>
          <ul className="ai-report__list">
            {points.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* 리스크요인은 스키마상 최소 1개 강제 → 항상 존재(장밋빛 방지). */}
      <div className="ai-report__block">
        <h4 className="ai-report__block-title">리스크 요인</h4>
        <ul className="ai-report__list ai-report__list--risk">
          {risks.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      </div>

      {report.국면정합성 ? (
        <div className="ai-report__block">
          <h4 className="ai-report__block-title">국면 정합성</h4>
          <p className="ai-report__fit">{report.국면정합성}</p>
        </div>
      ) : null}

      {/* 면책 고지 — 백엔드 스키마가 필수 필드로 강제. 리포트 하단 상시 노출(회색 톤). */}
      <p className="ai-report__disclaimer" role="note">
        {report.면책고지}
      </p>
    </div>
  )
}

// 과거 평가 히스토리 — created_at 내림차순(최신 우선). 국면 대비 종합의견 변화를 한눈에.
function HistoryList({ history }) {
  if (!history || history.length === 0) {
    return <div className="ai-report__history-empty">아직 생성된 과거 평가가 없습니다.</div>
  }
  return (
    <div className="ai-report__history">
      <h4 className="ai-report__block-title">과거 평가 (최신순)</h4>
      <ul className="ai-report__history-list">
        {history.map((h, i) => {
          const rj = h.report_json ?? {}
          const tone = opinionTone(rj.종합의견)
          return (
            <li key={i} className="ai-report__history-item">
              <span className={`badge badge--${tone}`}>{rj.종합의견 ?? '—'}</span>
              <span className="ai-report__history-meta">
                {formatTs(h.created_at)}
                {h.regime_at_creation ? ` · 국면 ${h.regime_at_creation}` : ''}
              </span>
              {rj.요약 ? <span className="ai-report__history-summary">{rj.요약}</span> : null}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

// ISO8601 → 로컬 표시. 파싱 실패면 원문 그대로(방어).
function formatTs(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
}
