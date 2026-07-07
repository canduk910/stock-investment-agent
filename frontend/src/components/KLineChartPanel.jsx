import { useEffect, useRef } from 'react'
import { init, dispose } from 'klinecharts'
import { candlesToKline } from '../lib/chartData.js'
import { readChartPalette } from '../lib/theme.js'

// klinecharts 는 `lines`/`bars` 배열 스타일을 '요소 통째 교체'로 병합한다 — 부분 객체({color}만)를
// 넘기면 dashedValue 등이 undefined 가 되어 그리기 중 크래시한다(내부 drawImp 가 dashedValue[0] 접근).
// 그래서 라인/바는 반드시 '완전한' 스타일 객체로 준다. (기본 팔레트는 주황·보라·핑크·청록이라 override 필수)
const fullLine = (color) => ({ style: 'solid', smooth: false, size: 1, dashedValue: [2, 2], color })
const fullBar = (p) => ({
  style: 'fill',
  borderStyle: 'solid',
  borderSize: 1,
  borderDashedValue: [2, 2],
  upColor: p.up,
  downColor: p.down,
  noChangeColor: p.down,
})

// 팔레트 테마 — theme.css 토큰(SSOT). 캔들 상승=빨강/하락=파랑(한국 관습·차트 한정 예외, p.up/p.down).
// 지표선(MA/RSI)·오버레이는 남색·회색으로 캔들색과 구분한다(빨/파 캔들과 안 겹치게). 초록·황색 없음.
function buildChartStyles(p) {
  return {
    grid: {
      show: true,
      horizontal: { color: p.grid },
      vertical: { color: p.grid },
    },
    candle: {
      bar: {
        upColor: p.up,
        downColor: p.down,
        noChangeColor: p.down,
        upBorderColor: p.up,
        downBorderColor: p.down,
        noChangeBorderColor: p.down,
        upWickColor: p.up,
        downWickColor: p.down,
        noChangeWickColor: p.down,
      },
      priceMark: {
        high: { color: p.axisText },
        low: { color: p.axisText },
        last: {
          upColor: p.up,
          downColor: p.down,
          noChangeColor: p.down,
          text: { color: p.white },
        },
      },
      tooltip: { text: { color: p.axisText } },
    },
    xAxis: {
      axisLine: { color: p.border },
      tickLine: { color: p.border },
      tickText: { color: p.axisText },
    },
    yAxis: {
      axisLine: { color: p.border },
      tickLine: { color: p.border },
      tickText: { color: p.axisText },
    },
    indicator: {
      // ohlc figure(기본 초록/빨강)도 팔레트로 대체 — 우리 지표엔 미사용이나 방어적으로 고정.
      ohlc: { upColor: p.up, downColor: p.down, noChangeColor: p.down },
      // 지표 선(MA/RSI 등) 팔레트 강제 — 남색·회색만(캔들 빨/파와 구분). 기본 팔레트의 난색을 전량 대체.
      lines: [
        fullLine(p.navy),
        fullLine(p.borderStrong),
        fullLine(p.navy),
        fullLine(p.borderStrong),
        fullLine(p.navy),
      ],
      bars: [fullBar(p)],
      lastValueMark: { text: { color: p.white } },
      tooltip: { text: { color: p.axisText } },
    },
    crosshair: {
      horizontal: { line: { color: p.borderStrong }, text: { backgroundColor: p.navy } },
      vertical: { line: { color: p.borderStrong }, text: { backgroundColor: p.navy } },
    },
  }
}

// 수집 데이터를 모두 실은 캔들차트: 메인 페인 캔들+MA / 서브페인 VOL·RSI / 52주 고저·현재가 수평선.
// 데이터: 번들 chart.candles → klinecharts KLineData(순수 매핑은 candlesToKline, chartData.test.js 로 고정).
// props: candles(번들 chart.candles), indicatorConfig({ma_period,rsi_period}), valuation(52주/현재가).
export default function KLineChartPanel({ candles, indicatorConfig, valuation }) {
  const containerRef = useRef(null)
  const chartRef = useRef(null)

  const maPeriod = indicatorConfig?.ma_period ?? 20
  const rsiPeriod = indicatorConfig?.rsi_period ?? 14

  // ① 생명주기: init → 테마·지표 세팅 → cleanup 에서 dispose(누수 방지). 지표 기간 변경 시 재구성.
  useEffect(() => {
    const el = containerRef.current
    if (!el) return undefined
    const chart = init(el)
    chartRef.current = chart
    if (!chart) return undefined

    const p = readChartPalette()
    // 버전 차이에 대비해 각 호출을 방어적으로 감싼다 — 하나가 실패해도 차트 전체가 죽지 않게.
    try {
      chart.setStyles(buildChartStyles(p))
    } catch (e) {
      /* 스타일 스키마 차이 무시 */
    }
    try {
      chart.createIndicator(
        {
          name: 'MA',
          calcParams: [maPeriod],
          styles: { lines: [fullLine(p.navy), fullLine(p.borderStrong)] },
        },
        false,
        { id: 'candle_pane' },
      )
    } catch (e) {
      /* noop */
    }
    try {
      chart.createIndicator({ name: 'VOL' }, false, { id: 'vol_pane' })
    } catch (e) {
      /* noop */
    }
    try {
      chart.createIndicator(
        { name: 'RSI', calcParams: [rsiPeriod], styles: { lines: [fullLine(p.navy)] } },
        false,
        { id: 'rsi_pane' },
      )
    } catch (e) {
      /* noop */
    }

    return () => {
      try {
        dispose(el)
      } catch (e) {
        /* noop */
      }
      chartRef.current = null
    }
  }, [maPeriod, rsiPeriod])

  // ② 데이터 주입 + 52주 고저·현재가 수평선 오버레이(현재가는 캐시 금지 원칙에 따라 매 조회 값 반영).
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    const data = candlesToKline(candles)
    try {
      chart.applyNewData(data)
    } catch (e) {
      /* noop */
    }

    // 기존 오버레이 제거 후 재생성 — 티커/현재가 갱신 시 선이 누적되지 않게.
    try {
      chart.removeOverlay()
    } catch (e) {
      /* noop */
    }
    const p = readChartPalette()
    // 52주 고저·현재가선은 남색·회색(캔들 빨/파와 구분). 고=회색 점선/저=회색 점선/현재가=남색 실선.
    const lines = []
    if (valuation?.week52_high != null)
      lines.push({ value: valuation.week52_high, color: p.borderStrong, style: 'dashed' })
    if (valuation?.week52_low != null)
      lines.push({ value: valuation.week52_low, color: p.borderStrong, style: 'dashed' })
    if (valuation?.price != null)
      lines.push({ value: valuation.price, color: p.navy, style: 'solid' })
    for (const l of lines) {
      try {
        chart.createOverlay({
          name: 'priceLine',
          points: [{ value: l.value }],
          lock: true,
          styles: {
            // 완전한 라인 스타일(dashedValue 포함) — 오버레이 그리기도 dashedValue 를 참조한다.
            line: { color: l.color, style: l.style, size: 1, dashedValue: [4, 4] },
            text: { color: p.white, backgroundColor: l.color },
          },
        })
      } catch (e) {
        /* 오버레이 실패해도 값은 카드/칩으로 별도 표시됨 */
      }
    }
  }, [candles, valuation])

  // ③ 반응형: 컨테이너 크기 변화 시 리사이즈.
  useEffect(() => {
    function onResize() {
      try {
        chartRef.current?.resize()
      } catch (e) {
        /* noop */
      }
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  return (
    <div
      className="kline"
      ref={containerRef}
      role="img"
      aria-label="가격 캔들차트 — 캔들·이동평균·거래량·RSI·52주 고저선"
    />
  )
}
