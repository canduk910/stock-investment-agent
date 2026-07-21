// 금일의 요약 — 최근 시황 리포트를 종합·중복제거해 최대 10줄 핵심메시지로. 시장국면 대시보드 **최상단**.
//   시각 강조 카드(주황 강조 소프트·📌). 종합=여러 시황 리포트 인용·면책(에이전트 시장 판정 아님).
//   **controlled/표시형** — 생성 상태·데이터는 상위(MacroDashboard)가 소유(자동 생성·하루 1회 재사용).
export default function DailySummary({ state = 'idle', data = null, errMsg = null, onGenerate }) {
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
          onClick={onGenerate}
          disabled={state === 'loading'}
        >
          {state === 'loading' ? '생성 중…' : state === 'done' ? '↻ 다시 생성' : '금일의 요약 생성'}
        </button>
      </div>
      {state === 'loading' && !data ? (
        <p className="daily-summary__loading" role="status">
          최신 시황을 종합하는 중…
        </p>
      ) : null}
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
