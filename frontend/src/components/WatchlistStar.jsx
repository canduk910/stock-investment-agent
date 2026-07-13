import { useEffect, useState } from 'react'
import { fetchWatchlistMembership, addWatchlist, removeWatchlist } from '../api.js'
import { isValidTicker } from '../lib/ticker.js'
import { addErrorMessage } from '../lib/watchlistLogic.js'

// 종목 리포트 헤더의 관심종목 별 토글(항목7) — 캡슐화 위젯. StockReport.jsx 토글 로직 이식.
//   실데이터(멤버십)는 여기가 직접 조회한다(환각 차단). 등록/해제는 **사용자 명시적 클릭으로만**
//   (자동 매매 아님). ★=등록완료(주황 강조)/☆=미등록(회색). 409(상한 30) 등 실패는 graceful 안내.
//   불량 ticker 는 렌더하지 않는다(잘못된 백엔드 조회 방지, ticker.js SSOT).
export default function WatchlistStar({ ticker, stockName }) {
  const [member, setMember] = useState(false)
  const [busy, setBusy] = useState(false)
  const [statusMsg, setStatusMsg] = useState('')
  const [isError, setIsError] = useState(false)

  const valid = isValidTicker(ticker)

  // 마운트/ticker 변경 시 멤버십 조회 → 버튼을 정확히 ★/☆ 로(IMP-21). 조회 실패는 조용히(☆ 폴백).
  useEffect(() => {
    if (!valid) return
    let cancelled = false
    setStatusMsg('')
    setIsError(false)
    ;(async () => {
      try {
        const m = await fetchWatchlistMembership(ticker)
        if (!cancelled) setMember(!!m?.member)
      } catch {
        if (!cancelled) setMember(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [ticker, valid])

  if (!valid) return null

  async function toggle() {
    if (busy) return
    setBusy(true)
    setIsError(false)
    try {
      if (member) {
        await removeWatchlist(ticker)
        setMember(false)
        setStatusMsg('관심종목에서 제거했습니다.')
      } else {
        await addWatchlist({ ticker, stockName })
        setMember(true)
        setStatusMsg('관심종목에 담았습니다.')
      }
    } catch (e) {
      // 409(상한 30) 등 status 별 안내(addErrorMessage) — 회색 중립 문구(주황·빨강 아님).
      setIsError(true)
      setStatusMsg(addErrorMessage(e?.status))
    } finally {
      setBusy(false)
    }
  }

  return (
    <span className="wl-star-wrap">
      <button
        type="button"
        className={`wl-star ${member ? 'is-on' : ''}`}
        onClick={toggle}
        disabled={busy}
        aria-pressed={member}
        aria-label={member ? '관심종목에서 제거' : '관심종목에 추가'}
        title={member ? '관심종목에 등록됨 — 클릭하면 제거' : '관심종목에 추가'}
      >
        <span className="wl-star__glyph" aria-hidden="true">
          {member ? '★' : '☆'}
        </span>
        <span className="wl-star__label">관심종목</span>
      </button>
      {statusMsg ? (
        <span
          className={`wl-star__status ${isError ? 'is-error' : ''}`}
          role="status"
          aria-live="polite"
        >
          {statusMsg}
        </span>
      ) : null}
    </span>
  )
}
