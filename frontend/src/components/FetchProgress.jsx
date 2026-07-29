// 리포트 수집·요약 진행 체크리스트 — SSE 이벤트를 실시간 표시(항목1).
// 목록 조회 중 → N건 발견(리스트) → 각 리포트 완료 틱(i/N 게이지) → 완료.
// 색은 theme.css 토큰만(뉴트럴 회색·중요=주황). 완료 방향색(빨강/파랑)은 가격 전용이라 여기선 미사용.

// SSE 이벤트(stage/found/progress) → progress 상태 리듀서(순수). done/error 는 컴포넌트가 별도 처리.
//   stage='list'(목록 조회 중) → 'found'(N건 발견·전부 pending) → 'progress'(개별 리포트 완료 틱).
export function applyProgressEvent(prev, ev) {
  const p = prev || { stage: 'list', reports: [], done: 0, total: 0 } // 첫 이벤트 전 기본 상태
  if (ev.type === 'stage') return { ...p, stage: ev.stage } // 단계만 갱신
  if (ev.type === 'found') {
    // 목록 확정 — 총건수·리스트 세팅(각 항목 pending 으로 초기화).
    return {
      ...p,
      stage: 'process',
      total: ev.reports.length,
      reports: ev.reports.map((r) => ({ ...r, status: 'pending' })),
    }
  }
  if (ev.type === 'progress') {
    // 개별 완료 — 해당 id 항목의 status 를 결과(new/skipped/failed)로 갱신, 진행 카운트 반영.
    return {
      ...p,
      done: ev.done,
      total: ev.total,
      reports: p.reports.map((r) => (r.id === ev.id ? { ...r, status: ev.result } : r)),
    }
  }
  return p // 알 수 없는 이벤트는 무시(상태 보존)
}

// 항목 상태 → 마크 글리프 / 라벨(뉴트럴 회색·방향색 아님).
const MARK = { pending: '⋯', new: '✓', skipped: '·', failed: '×' }
const STATUS_LABEL = { pending: '처리 중…', new: '새 요약', skipped: '기존', failed: '실패' }

// 진행 체크리스트 표시(순수 표시형) — progress 상태를 헤더·게이지·항목 리스트로.
export default function FetchProgress({ progress }) {
  if (!progress) return null
  const { stage, reports, done, total } = progress
  const pct = total > 0 ? Math.round((done / total) * 100) : 0 // 게이지 폭(%). total 0 이면 0(목록 조회 중)
  return (
    <div className="fetch-progress" role="status" aria-live="polite" aria-busy="true">
      <div className="fetch-progress__head">
        {stage === 'list' || total === 0
          ? '리포트 목록을 가져오는 중…'
          : `리포트 처리 중 · ${done}/${total}`}
      </div>
      {total > 0 ? (
        <div className="fetch-progress__bar" aria-hidden="true">
          <div className="fetch-progress__fill" style={{ width: `${pct}%` }} />
        </div>
      ) : null}
      {reports.length > 0 ? (
        <ul className="fetch-progress__list">
          {reports.map((r) => (
            <li key={r.id} className={`fetch-progress__item fetch-progress__item--${r.status}`}>
              <span className="fetch-progress__mark" aria-hidden="true">
                {MARK[r.status] ?? '⋯'}
              </span>
              <span className="fetch-progress__label">
                [{r.broker}] {r.title}
              </span>
              <span className="fetch-progress__status">{STATUS_LABEL[r.status] ?? ''}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
