import { yoyChange } from '../lib/reportLogic.js'

// 재무 추이 테이블 — financials.income(손익) + financials.ratio(주당·수익성).
// YoY 증감은 파랑(증가)/회색(감소)만 + ▲▼ 글리프 병기(색만으로 구분 금지, 디자인 시스템 §4).
// 난색(주황·빨강)은 절대 쓰지 않는다 — 재무 감소를 "위험"으로 오인시키지 않기 위함.

function fmtNum(n, digits = 0) {
  if (n === null || n === undefined || !Number.isFinite(Number(n))) return '—'
  const v = Number(n)
  return v.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

// '202412' → '24.12' (연.월 결산). 4자리면 그대로.
function fmtPeriod(period) {
  const s = String(period ?? '')
  if (s.length >= 6) return `${s.slice(2, 4)}.${s.slice(4, 6)}`
  return s
}

// 오름차순 정렬된 기간 배열 + 기간별 지표 병합 맵을 만든다(income·ratio 는 같은 기간을 공유).
function buildRows(income, ratio) {
  const byPeriod = new Map()
  const put = (arr) => {
    if (!Array.isArray(arr)) return
    for (const r of arr) {
      if (!r || r.period == null) continue
      const key = String(r.period)
      byPeriod.set(key, { ...(byPeriod.get(key) ?? { period: key }), ...r })
    }
  }
  put(income)
  put(ratio)
  return [...byPeriod.values()].sort((a, b) => String(a.period).localeCompare(String(b.period)))
}

// YoY 셀 — 값 + 전기 대비 방향 칩. pct=null(전기 0/음수/결측)이면 칩 생략.
function YoyValue({ value, prev, digits }) {
  const { pct, dir } = yoyChange(Number(value), Number(prev))
  const glyph = dir === 'up' ? '▲' : dir === 'down' ? '▼' : dir === 'flat' ? '─' : ''
  const cls = dir === 'up' ? 'up' : dir === 'down' ? 'down' : ''
  return (
    <>
      <span className="ftable__val">{fmtNum(value, digits)}</span>
      {pct !== null && dir ? (
        <span className={`ftable__yoy ${cls}`}>
          <span aria-hidden="true">{glyph}</span>
          {Math.abs(pct).toFixed(1)}%
        </span>
      ) : null}
    </>
  )
}

export default function FinancialTrendTable({ income, ratio }) {
  const rows = buildRows(income, ratio)

  if (rows.length === 0) {
    return <div className="ftable__empty">재무 데이터가 없습니다.</div>
  }

  return (
    <div className="ftable-wrap">
      {/* ① 손익 추이 — 매출·영업이익·순이익 + 전기 대비 YoY */}
      <table className="ftable" aria-label="손익 추이">
        <caption className="ftable__cap">손익 추이 <span>(억원, 전기 대비)</span></caption>
        <thead>
          <tr>
            <th scope="col">결산</th>
            <th scope="col" className="ftable__num-h">매출</th>
            <th scope="col" className="ftable__num-h">영업이익</th>
            <th scope="col" className="ftable__num-h">순이익</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const prev = i > 0 ? rows[i - 1] : {}
            return (
              <tr key={r.period}>
                <th scope="row">{fmtPeriod(r.period)}</th>
                <td className="ftable__num"><YoyValue value={r.revenue} prev={prev.revenue} digits={0} /></td>
                <td className="ftable__num"><YoyValue value={r.operating_income} prev={prev.operating_income} digits={0} /></td>
                <td className="ftable__num"><YoyValue value={r.net_income} prev={prev.net_income} digits={0} /></td>
              </tr>
            )
          })}
        </tbody>
      </table>

      {/* ② 주당·수익성 — EPS·BPS·ROE (ROE 는 전기 대비 방향) */}
      <table className="ftable" aria-label="주당·수익성 지표">
        <caption className="ftable__cap">주당·수익성 <span>(원 / %)</span></caption>
        <thead>
          <tr>
            <th scope="col">결산</th>
            <th scope="col" className="ftable__num-h">EPS</th>
            <th scope="col" className="ftable__num-h">BPS</th>
            <th scope="col" className="ftable__num-h">ROE</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const prev = i > 0 ? rows[i - 1] : {}
            return (
              <tr key={r.period}>
                <th scope="row">{fmtPeriod(r.period)}</th>
                <td className="ftable__num"><span className="ftable__val">{fmtNum(r.eps, 0)}</span></td>
                <td className="ftable__num"><span className="ftable__val">{fmtNum(r.bps, 0)}</span></td>
                <td className="ftable__num">
                  <YoyValue value={r.roe} prev={prev.roe} digits={1} />
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
