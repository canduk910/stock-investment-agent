import KLineChartPanel from './KLineChartPanel.jsx'
import StatCard from './StatCard.jsx'
import FinancialTrendTable from './FinancialTrendTable.jsx'
import AiReportPanel from './AiReportPanel.jsx'
import AnalystReportsSection from './AnalystReportsSection.jsx'
import { sectionFailed, isValuationReady } from '../lib/reportLogic.js'

// ── 표시 포맷 헬퍼(순수) — 값·판정은 백엔드 summary 가 확정, 여기선 표시만. 결측은 '—'. ──
function num(v, digits = 0) {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return '—'
  return Number(v).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}
function pct(v, digits = 1) {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return '—'
  return `${Number(v).toFixed(digits)}`
}
// CAGR 은 이미 %(엔진 stock/summary.py::_cagr 가 ×100 반환). 프론트는 ×100 재적용 금지(단위 규약).
function cagrPct(v, digits = 1) {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return '—'
  return `${Number(v).toFixed(digits)}`
}
function signDir(v) {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return null
  return Number(v) > 0 ? 'up' : Number(v) < 0 ? 'down' : 'flat'
}
function signedPct(v, digits = 2) {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return '—'
  const n = Number(v)
  return `${n > 0 ? '+' : ''}${n.toFixed(digits)}`
}

// 면책 고지 — LLM 없이 코드로 상시 고정 노출(회색 톤, 빨강 아님). RegimeGauge 문구 계승.
const DISCLAIMER =
  '본 리포트는 정보 제공 목적이며 투자 자문·매매 권유가 아닙니다. 모든 수치는 참고용이고, ' +
  '투자 판단과 그 결과에 대한 책임은 전적으로 본인에게 있습니다(면허 있는 투자자문 아님).'

// section 실패 판정 — partial_failure 에 있거나 데이터가 null 이면 "일시 조회 불가".
function failed(bundle, section) {
  return sectionFailed(bundle.partial_failure, section) || bundle[section] == null
}

export default function StockReportView({ bundle, sessionId, onConsult }) {
  if (!bundle) return null

  const { ticker, basic, valuation, financials, chart, summary, regime_gate } = bundle
  const indicatorConfig = bundle.indicator_config ?? { ma_period: 20, rsi_period: 14 }
  const sampleYears = summary?.sample_years
  const yearsLabel = sampleYears ? `${sampleYears}년` : 'N년'

  const valuationFailed = failed(bundle, 'valuation')
  const summaryFailed = failed(bundle, 'summary')
  const chartFailed = failed(bundle, 'chart') || !(chart?.candles?.length > 0)
  const financialsFailed = failed(bundle, 'financials')
  const valuationReady = !summaryFailed && isValuationReady(summary)

  // 예측 PER(리서치 컨센서스) — 후행 PER 착시 보완. forward_valuation 은 null(조회실패)/빈배열(미대상) 가능.
  const fwd = bundle.forward_valuation
  const fwdPers = (fwd?.forward_per ?? []).filter((x) => x.forward_per != null)
  const fwdReady = fwdPers.length > 0
  const latestFwd = fwdReady ? fwdPers[fwdPers.length - 1] : null // 가장 먼 추정연도(예 2027E)
  const estShort = (p) => (p ? `${String(p).slice(2, 4)}E` : '') // "202612" → "26E"
  // PER 추이: 직전년도(확정 실적) PER → 예측 PER(2026E·2027E). 모두 현재가 기준(동일 잣대).
  const perTrend = []
  if (fwd?.prev_year_per != null) {
    const y = fwd.prev_year_period ? String(fwd.prev_year_period).slice(0, 4) : '직전'
    perTrend.push(`직전(${y}) ${pct(fwd.prev_year_per, 1)}배`)
  }
  fwdPers.forEach((x) => perTrend.push(`${estShort(x.period)} ${pct(x.forward_per, 1)}배`))

  const changeDir = signDir(valuation?.change_rate)

  return (
    <section className="report" aria-label="종목 종합리포트">
      {/* ── 헤더: 종목명·업종 + 현재가·등락률(파랑/회색) ── */}
      <header className="report__head">
        <div className="report__id">
          <h2 className="report__name">
            {basic?.name ?? '종목'} <span className="report__ticker">{ticker}</span>
          </h2>
          <p className="report__sector">
            {basic?.sector ? basic.sector : failed(bundle, 'basic') ? '종목 정보 일시 조회 불가' : ''}
          </p>
        </div>
        <div className="report__price">
          {valuationFailed ? (
            <span className="report__price-fail">시세 일시 조회 불가</span>
          ) : (
            <>
              <span className="report__price-val">{num(valuation.price)}</span>
              <span className="report__price-unit">원</span>
              <span className={`report__change ${changeDir ?? ''}`}>
                <span aria-hidden="true">
                  {changeDir === 'up' ? '▲' : changeDir === 'down' ? '▼' : '─'}
                </span>{' '}
                {signedPct(valuation.change_rate)}%
              </span>
              {valuation.as_of ? <span className="report__asof">기준 {valuation.as_of}</span> : null}
            </>
          )}
        </div>
      </header>

      {/* ── 상단: 정량요약 카드 grid (숫자·판정은 코드 확정, LLM 미개입) ── */}
      <h3 className="report__section-label">정량 요약</h3>
      {summaryFailed ? (
        <div className="card card--failed report__section-fail">
          정량 요약 일시 조회 불가 · 나머지 섹션은 정상 표시
        </div>
      ) : (
        <div className="grid">
          <StatCard
            label={`매출 CAGR (${yearsLabel})`}
            value={cagrPct(summary.rev_cagr)}
            unit="%"
            subDir={signDir(summary.rev_cagr)}
            sub={summary.rev_cagr == null ? '표본 부족' : ' '}
          />
          <StatCard
            label={`영업이익 CAGR (${yearsLabel})`}
            value={cagrPct(summary.op_cagr)}
            unit="%"
            subDir={signDir(summary.op_cagr)}
            sub={summary.op_cagr == null ? '표본 부족' : ' '}
          />
          <StatCard
            label={`PER vs ${yearsLabel}평균`}
            value={valuationReady ? signedPct(summary.per_vs_avg, 1) : '준비 중'}
            unit={valuationReady ? '%' : ''}
            muted={!valuationReady}
            subDir={valuationReady ? signDir(summary.per_vs_avg) : null}
            meta={
              valuationReady
                ? `현재 ${pct(summary.current_per, 1)} · 평균 ${pct(summary.avg_per, 1)}`
                : '기준검증 전 — 임의 라벨 금지'
            }
          />
          <StatCard
            label="밸류에이션"
            badge={valuationReady ? { text: summary.valuation_label } : null}
            value={valuationReady ? null : '판정 준비 중'}
            muted={!valuationReady}
            meta={valuationReady ? `±10% 밴드 기준` : '데이터 검증 게이트'}
          />
          <StatCard
            label="예측 PER (직전→예측)"
            value={fwdReady ? pct(latestFwd.forward_per, 1) : '미제공'}
            unit={fwdReady ? '배' : ''}
            muted={!fwdReady}
            subDir={null}
            meta={fwdReady ? perTrend.join(' → ') : '리서치 미대상 종목'}
          />
          <StatCard
            label={`RSI (${indicatorConfig.rsi_period})`}
            value={pct(summary.rsi, 1)}
            subDir={null}
            meta={
              summary.ma20_gap_pct == null
                ? 'MA20 대비 —'
                : `MA${indicatorConfig.ma_period} 대비 ${signedPct(summary.ma20_gap_pct, 1)}%`
            }
          />
          <StatCard
            label="52주 위치"
            value={pct(summary.pos_52w_pct, 1)}
            unit="%"
            meta={
              valuation && !valuationFailed
                ? `${num(valuation.week52_low)} ~ ${num(valuation.week52_high)}원`
                : '고저 범위 —'
            }
          />
        </div>
      )}

      {/* 예측 PER 출처(투명성·환각차단) — 현재가 ÷ 리서치 컨센서스 예측 EPS. */}
      {fwdReady && fwd ? (
        <p className="report__est-source">
          예측 PER = 현재가 ÷ 컨센서스 예측 EPS · 출처 {fwd.analyst ?? '리서치'}
          {fwd.est_date ? ` · ${fwd.est_date} 기준` : ''}
          {fwd.recommendation ? ` · 투자의견 ${fwd.recommendation}` : ''}
        </p>
      ) : null}

      {/* ── 중단(focus): 기술적(캔들차트+국면정합성) · 기본적(재무추이) ── */}
      <h3 className="report__section-label">기술적 분석</h3>
      {chartFailed ? (
        <div className="card card--failed report__section-fail">
          차트 데이터 일시 조회 불가 · 나머지 섹션은 정상 표시
        </div>
      ) : (
        <div className="report__chart-block">
          <KLineChartPanel
            candles={chart.candles}
            indicatorConfig={indicatorConfig}
            valuation={valuationFailed ? null : valuation}
          />
          {/* 오버레이 라벨 렌더가 실패해도 값을 읽도록 칩으로 병기(색: 파랑/남색/회색) */}
          {!valuationFailed && (
            <div className="report__chips">
              <span className="chip chip--up">현재가 {num(valuation.price)}원</span>
              <span className="chip chip--navy">52주 최고 {num(valuation.week52_high)}원</span>
              <span className="chip chip--down">52주 최저 {num(valuation.week52_low)}원</span>
            </div>
          )}
        </div>
      )}

      {/* 국면 정합성 — regime_gate.note(사실 서술), 국면명은 주황(강조). 매매 명령형 아님. */}
      {regime_gate && !failed(bundle, 'regime_gate') ? (
        <div className="regime-fit">
          <div className="regime-fit__head">
            국면 정합성 · 현재 국면 <span className="regime-fit__name">{regime_gate.regime}</span>
            {regime_gate.entry_blocked ? (
              <span className="regime-fit__flag">신규 진입 주의</span>
            ) : null}
          </div>
          {regime_gate.note ? <p className="regime-fit__note">{regime_gate.note}</p> : null}
          <div className="regime-fit__meta">
            {regime_gate.per_max != null ? `PER 기준 ≤ ${regime_gate.per_max}` : 'PER 기준 —'}
            {' · '}
            {regime_gate.pbr_max != null ? `PBR 기준 ≤ ${regime_gate.pbr_max}` : 'PBR 기준 —'}
            {regime_gate.per_over ? ' · PER 기준 초과' : ''}
            {regime_gate.pbr_over ? ' · PBR 기준 초과' : ''}
          </div>
        </div>
      ) : null}

      <h3 className="report__section-label">기본적 분석 · 재무 추이</h3>
      {financialsFailed ? (
        <div className="card card--failed report__section-fail">
          재무 데이터 일시 조회 불가 · 나머지 섹션은 정상 표시
        </div>
      ) : (
        <FinancialTrendTable income={financials.income} ratio={financials.ratio} />
      )}

      {/* ── 하단: AI 종합 서술(W10 P2, 요청 시 생성) + 면책고지(코드 고정 상시노출) ── */}
      <h3 className="report__section-label">AI 종합 서술</h3>
      <AiReportPanel ticker={ticker} />

      {/* ── 애널리스트 리포트 요약(네이버 수집) + "이 리포트로 상담하기"(세션 컨텍스트 연계) ── */}
      <AnalystReportsSection ticker={ticker} sessionId={sessionId} onConsult={onConsult} />

      <p className="report__disclaimer" role="note">
        {DISCLAIMER}
      </p>
    </section>
  )
}
