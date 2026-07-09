// 종목코드 유효성 — 앱 전체 SSOT(단일 출처). 직접입력(StockReport.onSubmit)과
// 팝업 라우팅(popupRouter.routePopup)이 이 하나의 규칙을 공유한다. 두 경로가 서로 다른 규칙을
// 쓰면 "직접입력은 받는데 팝업은 거부" 같은 UX 불일치가 생긴다.
//
// 규칙: `[0-9A-Za-z]{6}`(6자 영숫자). 한국 단축코드는 대개 6자리 숫자지만 일부는 영문을 포함한다.
// 목적은 numeric 강제가 아니라 "명백한 불량(종목명·부분입력) 차단"이다.
const TICKER_RE = /^[0-9A-Za-z]{6}$/

export function isValidTicker(ticker) {
  return typeof ticker === 'string' && TICKER_RE.test(ticker)
}
