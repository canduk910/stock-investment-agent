import { useState } from 'react'
import KLineChartPanel from './KLineChartPanel.jsx'
import { useFetch } from '../lib/useFetch.js'
import { fetchStockChart } from '../api.js'

// 종목 차트 섹션 — 주기(일봉/주봉) × 기간(3개월/1년/3년/10년) 선택 + 캔들 스왑.
// 판정(대순환·요약)은 백엔드; 여기선 표시 차트만 교체한다. **정량 요약·GrandCyclePanel 은 번들(일봉)에
// pin**(부모가 유지) — 차트 탐색이 정량 판정을 바꾸지 않게. 스테이지 리본은 표시 시계열로 재계산됨.
// 초기·로딩·에러 시엔 부모가 준 번들 차트(fallback)를 그대로 보여 빈 화면·깜빡임을 막는다.

// 봉 주기 선택지 — KIS FID_PERIOD_DIV_CODE(D/W)와 매핑. 라벨은 표시용.
const PERIODS = [
  { key: 'D', label: '일봉' },
  { key: 'W', label: '주봉' },
]
// 조회 기간 선택지 — 백엔드 _CHART_RANGE_DAYS 와 SSOT. 10년은 date-window 페이지네이션으로 조회.
const RANGES = [
  { key: '3m', label: '3개월' },
  { key: '1y', label: '1년' },
  { key: '3y', label: '3년' },
  { key: '10y', label: '10년' },
]

// props: ticker + fallback*(부모가 번들[일봉]에서 준 초기 차트/리본/현재단계). indicatorConfig(MA/RSI),
//   valuation(52주·현재가선). fallback 은 조회 전·재조회 중·실패 시 표시 소스로 쓴다(빈 화면 방지).
export default function ChartSection({
  ticker,
  fallbackCandles,
  fallbackSegments,
  fallbackStage,
  indicatorConfig,
  valuation,
}) {
  const [period, setPeriod] = useState('D') // 봉 주기(기본 일봉)
  const [range, setRange] = useState('1y') // 조회 기간(기본 1년)

  // 선택 변경 시 재조회. useFetch 는 재조회 중 이전 data 를 유지 → 스왑 전까지 이전 차트가 남아 부드럽다.
  const { data, loading, error } = useFetch(
    () => fetchStockChart(ticker, period, range),
    [ticker, period, range],
  )

  // 표시 소스: 조회 성공 시 그 데이터, 아직/실패면 번들 차트(fallback) — 빈 화면 방지.
  const displayed = data ?? {
    candles: fallbackCandles,
    stage_segments: fallbackSegments,
    current_stage: fallbackStage,
  }

  return (
    <div className="chart-section">
      <div className="report__chart-toolbar" role="toolbar" aria-label="차트 주기·기간 선택">
        <div className="chart-controls__group">
          <span className="chart-controls__label">봉 주기</span>
          <div className="chart-controls__seg">
            {PERIODS.map((p) => (
              <button
                key={p.key}
                type="button"
                className="chart-control-btn"
                aria-pressed={period === p.key}
                disabled={loading}
                onClick={() => setPeriod(p.key)}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
        <div className="chart-controls__group">
          <span className="chart-controls__label">기간</span>
          <div className="chart-controls__seg">
            {RANGES.map((r) => (
              <button
                key={r.key}
                type="button"
                className="chart-control-btn"
                aria-pressed={range === r.key}
                disabled={loading}
                onClick={() => setRange(r.key)}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>
        {loading ? (
          <span className="chart-controls__status" role="status">
            불러오는 중…
          </span>
        ) : error ? (
          <span className="chart-controls__status chart-controls__status--muted" role="status">
            일시 조회 실패 · 이전 차트 유지
          </span>
        ) : null}
      </div>

      {/* 캔들 렌더 — 표시 시계열(displayed) 기준으로 3MA·스테이지 리본을 그린다(주기/기간 따라감).
          단, 정량 요약·GrandCyclePanel 은 부모가 번들[일봉]에 pin(여기서 안 바꿈). */}
      <KLineChartPanel
        candles={displayed.candles}
        indicatorConfig={indicatorConfig}
        valuation={valuation}
        stageSegments={displayed.stage_segments}
        currentStage={displayed.current_stage}
      />
    </div>
  )
}
