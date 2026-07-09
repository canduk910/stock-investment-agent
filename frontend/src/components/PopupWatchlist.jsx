// 챗 팝업(show_watchlist) 본문 — 워치리스트는 WEEK 10 범위이므로 플레이스홀더로 표시한다.
// 라우팅 계약(show_watchlist → watchlist)은 지금 확정하고, 실데이터·정렬은 W10 에서 채운다.
export default function PopupWatchlist({ args }) {
  const sortBy = args?.sort_by
  const sortLabel =
    { registered: '등록순', change_rate: '등락률순', near_target: '목표가 근접순' }[sortBy] ?? null
  return (
    <div className="popup__placeholder">
      <p className="popup__placeholder-title">관심종목(워치리스트)</p>
      <p>
        관심종목 목록·정렬·목표가 알림은 <strong>WEEK 10</strong>에서 제공됩니다.
        {sortLabel ? ` (요청 정렬: ${sortLabel})` : ''}
      </p>
    </div>
  )
}
