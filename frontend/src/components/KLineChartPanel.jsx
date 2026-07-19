import { useEffect, useRef } from 'react'
import { init, dispose, registerOverlay } from 'klinecharts'
import { candlesToKline, dateToTimestamp } from '../lib/chartData.js'
import { readChartPalette } from '../lib/theme.js'
import { ribbonSegments } from '../lib/grandCycle.js'

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

// ── 대순환 스테이지 리본 오버레이 ─────────────────────────────────────────────
// 캔들 하단에 얇은 띠(구간별 rect + 번호/글리프 라벨)로 "언제 어느 대순환 단계였는가"를 표시한다.
// klinecharts 커스텀 오버레이(registerOverlay+createPointFigures)로 캔들 좌표계에 정렬 → 팬·줌 따라감.
// 색: 국면 뉴트럴 톤(상승/전환/하락)·현재 주황(extendData). **방향은 색이 아니라 글리프(▲▼◆)**.
const RIBBON_H = 18 // 리본 높이(px)

// 국면 → 리본 배경 톤(방향색·경보색 아님). 현재 구간은 주황 소프트.
function phaseTint(p, seg) {
  if (seg.isCurrent) return p.emphSoft
  if (seg.phase === '상승') return p.surface2
  if (seg.phase === '하락') return p.flatSoft
  return p.surface3 // 전환·미상 → 가장 옅은 뉴트럴
}

// 오버레이 템플릿 등록 — klinecharts 는 같은 name 재등록을 덮어쓰기(idempotent)라 마운트마다 호출해도
// 안전하다(전역 플래그 없이 → 테스트 격리도 단순). 실패는 graceful(리본만 생략).
function ensureStageBandOverlay() {
  try {
    registerOverlay({
      name: 'gcStageBand',
      totalStep: 3, // 2점 → 완성(그리기 모드 아님)
      needDefaultPointFigure: false,
      needDefaultXAxisFigure: false,
      needDefaultYAxisFigure: false,
      createPointFigures: ({ overlay, coordinates, bounding }) => {
        if (!coordinates || coordinates.length < 2) return []
        const left = Math.max(0, Math.min(coordinates[0].x, coordinates[1].x))
        const right = Math.min(bounding.width, Math.max(coordinates[0].x, coordinates[1].x))
        if (right <= 0 || left >= bounding.width || right - left < 1) return [] // 화면 밖·폭 0
        const width = right - left
        const y = bounding.height - RIBBON_H
        const ed = overlay.extendData || {}
        const figures = [
          {
            type: 'rect',
            attrs: { x: left, y, width, height: RIBBON_H },
            styles: {
              style: 'stroke_fill',
              color: ed.bg,
              borderColor: ed.border,
              borderSize: 1,
              borderStyle: 'solid',
            },
            ignoreEvent: true,
          },
        ]
        // 라벨(번호+글리프)은 폭이 충분할 때만(좁은 슬리버는 겹침/과밀 방지 → 띠만).
        if (width >= 16 && ed.label) {
          figures.push({
            type: 'text',
            attrs: {
              x: left + width / 2,
              y: y + RIBBON_H / 2,
              text: ed.label,
              align: 'center',
              baseline: 'middle',
            },
            styles: { color: ed.text, size: 10, weight: ed.isCurrent ? 'bold' : 'normal' },
            ignoreEvent: true,
          })
        }
        return figures
      },
    })
  } catch (e) {
    /* 등록 실패해도 차트/MA/priceLine 정상 — 리본만 생략(방어) */
  }
}

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
export default function KLineChartPanel({
  candles,
  indicatorConfig,
  valuation,
  stageSegments,
  currentStage,
}) {
  const containerRef = useRef(null)
  const chartRef = useRef(null)

  const maPeriod = indicatorConfig?.ma_period ?? 20
  const rsiPeriod = indicatorConfig?.rsi_period ?? 14

  // 고지로 대순환 3MA(단기/중기/장기) 오버레이 — indicatorConfig.grand_cycle.periods(SSOT).
  // 있으면 단일 MA20 대신 3선을 그려 배열(정배열/역배열)을 눈으로 확인. 없으면 기존 MA20 폴백.
  const gcp = indicatorConfig?.grand_cycle?.periods
  const maShort = gcp?.short ?? null
  const maMedium = gcp?.medium ?? null
  const maLong = gcp?.long ?? null

  // ① 생명주기: init → 테마·지표 세팅 → cleanup 에서 dispose(누수 방지). 지표 기간 변경 시 재구성.
  useEffect(() => {
    const el = containerRef.current
    if (!el) return undefined
    ensureStageBandOverlay() // 대순환 리본 오버레이 템플릿 등록(전역·1회·guarded)
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
      // 대순환 3MA(단기 주황·중기 회색·장기 남색)로 배열을 시각화. 색은 강조 주황/중립색(방향색 아님).
      // 기간·색이 calcParams·lines 순서로 1:1 대응. grand_cycle 없으면 기존 단일 MA20 로 폴백.
      const gc3 = maShort != null && maMedium != null && maLong != null
      const calcParams = gc3 ? [maShort, maMedium, maLong] : [maPeriod]
      const lines = gc3
        ? [fullLine(p.emph), fullLine(p.borderStrong), fullLine(p.navy)]
        : [fullLine(p.navy), fullLine(p.borderStrong)]
      chart.createIndicator(
        { name: 'MA', calcParams, styles: { lines } },
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
  }, [maPeriod, rsiPeriod, maShort, maMedium, maLong])

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

    // 대순환 스테이지 리본 — 구간(날짜 키)별 하단 띠. 판정·구간은 백엔드, 여기선 표시만.
    //   좌표는 timestamp(dateToTimestamp)로 캔들축 정렬. 실패는 graceful(차트/MA/priceLine 불변).
    const segs = ribbonSegments(stageSegments, indicatorConfig?.grand_cycle, currentStage)
    for (const seg of segs) {
      try {
        chart.createOverlay({
          name: 'gcStageBand',
          lock: true,
          points: [
            { timestamp: dateToTimestamp(seg.start_date) },
            { timestamp: dateToTimestamp(seg.end_date) },
          ],
          extendData: {
            bg: phaseTint(p, seg),
            border: p.borderStrong,
            text: seg.isCurrent ? p.emphStrong : p.axisText,
            label: `${seg.stage}${seg.glyph}`,
            isCurrent: seg.isCurrent,
          },
        })
      } catch (e) {
        /* 세그먼트 리본 실패 graceful */
      }
    }
  }, [candles, valuation, stageSegments, currentStage, indicatorConfig])

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

  const hasRibbon = Array.isArray(stageSegments) && stageSegments.length > 0

  return (
    <div className="kline-wrap">
      <div
        className="kline"
        ref={containerRef}
        role="img"
        aria-label="가격 캔들차트 — 캔들·이동평균·거래량·RSI·52주 고저선·대순환 스테이지 리본"
      />
      {hasRibbon && (
        <p className="kline__ribbon-legend">
          하단 띠 = 이동평균 대순환 단계(①~⑥) · <b>▲</b>상승 <b>▼</b>하락 <b>◆</b>전환 ·{' '}
          <span className="kline__ribbon-now">주황=현재</span>
        </p>
      )}
    </div>
  )
}
