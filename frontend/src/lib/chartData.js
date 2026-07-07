// 차트 데이터 매핑 — 번들 chart.candles → klinecharts KLineData 로 변환하는 순수 로직.
// klinecharts 자체(캔버스)는 여기서 다루지 않는다(경계). 이 파일은 브라우저 없이 테스트 가능하다.
// TDD: chartData.test.js 가 이 함수들의 계약(날짜→timestamp, 정렬·정규화)을 고정한다.

const DATE_RE = /^\d{8}$/

// 'YYYYMMDD'(또는 8자리 숫자) → UTC 자정 epoch(ms). 결정적이도록 UTC 기준으로 고정한다
// (로컬 타임존에 따라 일자가 밀리지 않게). 형식·범위가 잘못되면 null(임의 날짜로 렌더 금지).
export function dateToTimestamp(dateStr) {
  if (dateStr === null || dateStr === undefined) return null
  const s = String(dateStr)
  if (!DATE_RE.test(s)) return null
  const year = Number(s.slice(0, 4))
  const month = Number(s.slice(4, 6))
  const day = Number(s.slice(6, 8))
  if (month < 1 || month > 12 || day < 1 || day > 31) return null
  const ts = Date.UTC(year, month - 1, day)
  // 존재하지 않는 날짜(예: 0230)는 롤오버되므로 역변환으로 검증한다.
  const d = new Date(ts)
  if (d.getUTCFullYear() !== year || d.getUTCMonth() !== month - 1 || d.getUTCDate() !== day) {
    return null
  }
  return ts
}

// 숫자 강제 변환(콤마·문자열 허용). 유한수가 아니면 null.
function toNum(v) {
  if (v === null || v === undefined || v === '') return null
  const n = typeof v === 'string' ? Number(v.replace(/,/g, '')) : Number(v)
  return Number.isFinite(n) ? n : null
}

// 번들 chart.candles[{date:'YYYYMMDD',open,high,low,close,volume}]
//   → klinecharts KLineData[{timestamp, open, high, low, close, volume}].
// - date 파싱 불가 또는 OHLC 중 하나라도 결측이면 그 행은 조용히 제외한다(임의값 주입 금지).
// - volume 결측은 0 으로 채운다(거래량 서브페인 렌더용, OHLC 와 달리 0 은 유효).
// - klinecharts 는 timestamp 오름차순을 요구하므로 정렬해서 반환한다.
export function candlesToKline(candles) {
  if (!Array.isArray(candles)) return []
  const out = []
  for (const c of candles) {
    if (!c) continue
    const timestamp = dateToTimestamp(c.date)
    if (timestamp === null) continue
    const open = toNum(c.open)
    const high = toNum(c.high)
    const low = toNum(c.low)
    const close = toNum(c.close)
    if (open === null || high === null || low === null || close === null) continue
    const volume = toNum(c.volume) ?? 0
    out.push({ timestamp, open, high, low, close, volume })
  }
  out.sort((a, b) => a.timestamp - b.timestamp)
  return out
}
