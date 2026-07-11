import { useEffect, useState } from 'react'
import { fetchBalance } from '../api.js'

// 잔고(포트폴리오) 패널 — 우측 동적 패널에서 /api/balance 를 자체 조회한다(환각 차단).
// 조회 전용(주문/매매 없음). 현재가 포함 → 무캐시(팝업 열 때마다 조회, 원칙1).
// 네이비 히어로 카드(순자산 + 평가손익 pill) + 보조 카드 4(예수금·매입·평가·보유종목) + 보유종목 표.
// 손익 색 = 글로벌 방향 규칙(수익=빨강 --c-up / 손실=파랑 --c-down / 보합=회색 --c-flat) — 리디자인 반영.
//   손실은 파랑이며 빨강 경보(--c-danger)는 쓰지 않는다(경보는 채움 배너/칩 전용). 색만으로 구분 금지 → ▲▼─ 병기.
// 부분실패(KIS 조회 실패, partial_failure:['balance'])는 dashed "일시 조회 불가" 카드(전체 에러 화면 아님).
// 면책 상시 노출(잔고 표시일 뿐 리밸런싱 조언·매매 권유 아님). 색은 theme.css 토큰만.

const DISCLAIMER =
  '본 화면은 정보 제공 목적이며 투자 자문·매매 권유가 아닙니다. 잔고·평가액은 조회 시점 기준이며 ' +
  '판정·수치는 코드가 산출합니다. 투자 판단과 그 결과의 책임은 전적으로 본인에게 있습니다.'

// 원 단위 정수 포맷(천단위 콤마). 결측/비수치 → '—'.
const won = (v) => {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return '—'
  return `${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}원`
}
// 부호 있는 원(손익 금액). +는 명시, 결측 → '—'.
const signedWon = (v) => {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return '—'
  const n = Number(v)
  return `${n > 0 ? '+' : ''}${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}원`
}
// 부호 있는 퍼센트(수익률).
const signedPct = (v) => {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return '—'
  const n = Number(v)
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`
}
// 수량(정수).
const qty = (v) => {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return '—'
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })
}
// 방향(상승/하락/중립) — 색·글리프 결정. 상승=파랑(up)/하락=회색(down)/0·결측=flat.
const dir = (v) => {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return 'flat'
  return Number(v) > 0 ? 'up' : Number(v) < 0 ? 'down' : 'flat'
}

// partial_failure(문자열 리스트/객체 둘 다 방어)에 key 가 있는지.
function inPartialFailure(partialFailure, key) {
  if (!Array.isArray(partialFailure)) return false
  return partialFailure.some((e) => (typeof e === 'string' ? e === key : e?.section === key))
}

// 요약 카드 1개 — 라벨 + 값. emph=true 면 강조(순자산). 손익 카드는 방향색(up/down) 적용.
function SummaryCard({ label, value, tone }) {
  return (
    <div className={`balance__card ${tone ? `balance__card--${tone}` : ''}`}>
      <span className="balance__card-label">{label}</span>
      <span className="balance__card-value">{value}</span>
    </div>
  )
}

// 손익 표기(금액+수익률) — 방향색 + 글리프(색만으로 구분하지 않음, 디자인 §4).
function Pnl({ amount, pct }) {
  const d = dir(amount ?? pct)
  return (
    <span className={`balance__pnl ${d}`}>
      <span aria-hidden="true">{d === 'up' ? '▲' : d === 'down' ? '▼' : '─'}</span>{' '}
      {signedWon(amount)}
      {pct !== null && pct !== undefined && Number.isFinite(Number(pct)) ? (
        <span className="balance__pnl-pct"> ({signedPct(pct)})</span>
      ) : null}
    </span>
  )
}

export default function BalancePanel() {
  const [view, setView] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      // partial_failure 는 200 정상 응답이라 throw 안 함(그대로 렌더). throw 는 네트워크/HTTP 오류만.
      setView(await fetchBalance())
    } catch (e) {
      setError(e.message)
      setView(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  if (loading && !view) {
    return <div className="balance__state">잔고를 불러오는 중…</div>
  }
  // 네트워크/HTTP 오류(백엔드 미연결 등) — 재시도(무한 스피너 금지). 면책은 항상.
  if (error || !view) {
    return (
      <div className="balance">
        <div className="banner banner--warn balance__error" role="status">
          잔고를 불러오지 못했습니다({error ?? '데이터 없음'}).
          <button type="button" className="banner__retry" onClick={load}>
            ↻ 재시도
          </button>
        </div>
        <p className="balance__disclaimer" role="note">{DISCLAIMER}</p>
      </div>
    )
  }

  const balanceFailed = view.holdings == null || inPartialFailure(view.partial_failure, 'balance')
  const summary = view.summary ?? null
  const holdings = Array.isArray(view.holdings) ? view.holdings : []

  // KIS 조회 실패(부분실패) — "일시 조회 불가" 안내. 전체 에러 화면 아님(면책·재시도 유지).
  if (balanceFailed) {
    return (
      <div className="balance">
        <div className="balance__partial-card" role="status">
          <p className="balance__partial-text">
            잔고를 일시 조회 불가합니다 (증권사 응답 지연). 잠시 후 다시 시도해 주세요.
          </p>
          <button type="button" className="refresh balance__partial-retry" onClick={load}>
            ↻ 재시도
          </button>
        </div>
        <p className="balance__disclaimer" role="note">{DISCLAIMER}</p>
      </div>
    )
  }

  return (
    <div className="balance">
      {/* ── 네이비 히어로 카드: 순자산 + 평가손익 pill ── */}
      {summary ? (
        <>
          <div className="balance__hero">
            <div className="balance__hero-main">
              <span className="balance__hero-label">순자산</span>
              <span className="balance__hero-value">{won(summary.net_asset)}</span>
            </div>
            <span className={`balance__hero-pnl ${dir(summary.pnl_amount)}`}>
              <span aria-hidden="true">
                {dir(summary.pnl_amount) === 'up' ? '▲' : dir(summary.pnl_amount) === 'down' ? '▼' : '─'}
              </span>{' '}
              {signedWon(summary.pnl_amount)} 평가손익
            </span>
          </div>

          {/* ── 보조 카드 4: 예수금·매입액·평가액·보유종목 ── */}
          <div className="balance__summary">
            <SummaryCard label="예수금" value={won(summary.deposit)} />
            <SummaryCard label="매입금액" value={won(summary.purchase_amount)} />
            <SummaryCard label="평가금액" value={won(summary.eval_amount)} />
            <SummaryCard label="보유 종목" value={`${holdings.length}종목`} />
          </div>
        </>
      ) : null}

      {/* ── 보유종목 표 ── */}
      {holdings.length === 0 ? (
        <div className="balance__empty">보유 종목이 없습니다.</div>
      ) : (
        <div className="balance__table-wrap">
          <table className="balance__table">
            <thead>
              <tr>
                <th scope="col">종목</th>
                <th scope="col" className="balance__num">수량</th>
                <th scope="col" className="balance__num">평단가</th>
                <th scope="col" className="balance__num">현재가</th>
                <th scope="col" className="balance__num">평가금액</th>
                <th scope="col" className="balance__num">평가손익</th>
              </tr>
            </thead>
            <tbody>
              {holdings.map((h) => (
                <tr key={h.ticker}>
                  <th scope="row" className="balance__name-cell">
                    <span className="balance__name">{h.name ?? h.ticker}</span>
                    <span className="balance__ticker">{h.ticker}</span>
                  </th>
                  <td className="balance__num">{qty(h.qty)}</td>
                  <td className="balance__num">{won(h.avg_price)}</td>
                  <td className="balance__num">{won(h.current_price)}</td>
                  <td className="balance__num">{won(h.eval_amount)}</td>
                  <td className="balance__num">
                    <Pnl amount={h.pnl_amount} pct={h.pnl_pct} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="balance__asof" role="note">
        조회 시점 기준(현재가 포함, 캐시 없음) · 시세는 실시간 직접 조회
      </p>
      <p className="balance__disclaimer" role="note">{DISCLAIMER}</p>
    </div>
  )
}
