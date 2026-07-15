import WatchlistView from './WatchlistView.jsx'

// 챗 팝업(show_watchlist) 본문 — WatchlistView 를 얇게 감싼다(팝업·독립페이지가 동일 본문 공유).
// 실데이터·정렬·목표가 알림은 WatchlistView 가 담당한다(LLM 응답이 아니라 프론트가 직접 조회 — 환각 차단).
// LLM 은 args.sort_by(enum)만 준다 → 초기 정렬만 반영하고, 이후 재정렬은 프론트 순수 로직.
export default function PopupWatchlist({ args, onOpenStock }) {
  return <WatchlistView initialSortBy={args?.sort_by} onOpenStock={onOpenStock} />
}
