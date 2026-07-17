import { grandCycleStages, stageGlyph, bandReadout, grandCycleInsight } from '../lib/grandCycle.js'

// 고지로 이동평균선 대순환 카드 — 기술적 분석 섹션 하단. 판정(단계·밴드·전환)은 백엔드 엔진이,
// 여기서는 결과를 표시만: 현재 단계 배지 + 6단계 사이클 스텝(현재만 주황 강조·글리프로 방향) +
// 밴드/지속 readout + 방법론 인용 인사이트 + 면책(고정). 색은 theme.css 토큰(주황 강조만, 방향색 아님).
//
// props:
//   cycle   = bundle.summary.ma_grand_cycle (계산 결과 or null[봉부족])
//   catalog = bundle.indicator_config.grand_cycle (6단계 라벨·기간 SSOT; 없으면 스텝 생략)
function fmtNum(x) {
  if (x == null || !Number.isFinite(Number(x))) return '—'
  const n = Number(x)
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

export default function GrandCyclePanel({ cycle, catalog }) {
  const steps = cycle ? grandCycleStages(catalog, cycle.stage) : []
  const periods = cycle?.periods || catalog?.periods || {}
  const ma = cycle?.ma || {}

  return (
    <section className="grand-cycle" aria-label="이동평균선 대순환">
      <div className="grand-cycle__head">
        <span className="grand-cycle__title">이동평균선 대순환 · 고지로</span>
        <span className="grand-cycle__tag">기술적 분석 심화 · 참고용</span>
      </div>

      {!cycle ? (
        <div className="grand-cycle__empty">
          최근 거래일 봉이 부족해 대순환 분석을 보류합니다.
        </div>
      ) : (
        <>
          <div className="grand-cycle__current">
            <span className="grand-cycle__badge">
              {cycle.stage != null ? `${cycle.stage}단계` : '판정 보류'}
            </span>
            <span className="grand-cycle__stage-name">{cycle.stage_name || '—'}</span>
            {cycle.arrangement ? (
              <span className="grand-cycle__arr">{cycle.arrangement}</span>
            ) : null}
          </div>

          {steps.length > 0 ? (
            <ol className="grand-cycle__steps" aria-label="6단계 사이클">
              {steps.map((s) => (
                <li
                  key={s.stage}
                  className={`grand-cycle__step${s.isCurrent ? ' grand-cycle__step--current' : ''}`}
                  aria-current={s.isCurrent ? 'step' : undefined}
                >
                  <span className="grand-cycle__step-glyph" aria-hidden="true">
                    {stageGlyph(s.phase)}
                  </span>
                  <span className="grand-cycle__step-no">{s.stage}</span>
                  <span className="grand-cycle__step-name">{s.name}</span>
                </li>
              ))}
            </ol>
          ) : null}

          <div className="grand-cycle__readouts">
            <div className="grand-cycle__readout">
              <span className="grand-cycle__readout-label">밴드(단기−장기)</span>
              <span className="grand-cycle__readout-value">{bandReadout(cycle)}</span>
            </div>
            <div className="grand-cycle__readout">
              <span className="grand-cycle__readout-label">현재 단계 지속</span>
              <span className="grand-cycle__readout-value">{cycle.bars_in_stage}봉</span>
            </div>
            <div className="grand-cycle__readout">
              <span className="grand-cycle__readout-label">
                이동평균({periods.short}/{periods.medium}/{periods.long})
              </span>
              <span className="grand-cycle__readout-value">
                {fmtNum(ma.short)} · {fmtNum(ma.medium)} · {fmtNum(ma.long)}
              </span>
            </div>
          </div>

          <p className="grand-cycle__insight">{grandCycleInsight(cycle)}</p>

          <p className="grand-cycle__disclaimer">
            이동평균선 대순환은 규칙 기반 기술적 참고 지표이며, 특정 종목의 매매를 권유하지 않습니다.
            투자 판단과 책임은 본인에게 있습니다.
          </p>
        </>
      )}
    </section>
  )
}
