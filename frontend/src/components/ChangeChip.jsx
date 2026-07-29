import { changeDir, dirGlyph, signedNum } from '../lib/format.js'

// 등락률(%) 칩 SSOT — 관심종목(WatchlistView)·스크리너(ScreenerPanel)·종목리포트(StockReportView)가
// 같은 마크업을 각자 복제하던 것을 통합(Sparkline/DkMonogram 공용화 선례와 동형).
//
// 표시 규칙(팔레트·접근성 계약):
//   - 방향색은 CSS 클래스(up/down — theme.css 방향색 토큰)로만, 색만으로 구분하지 않도록
//     ▲▼─ 글리프(dirGlyph)를 aria-hidden 으로 병기한다.
//   - 값은 signedNum(부호 있는 소수·% 접미사는 여기서 붙임), 결측은 '—%'가 아니라 dir=null
//     (기본 회색·글리프 ─)로 graceful.
//   - className 으로 자리별 기본 클래스를 주입(관심종목·스크리너 'wl__change' / 리포트 'report__change')
//     — 시각 차이는 CSS 가 소유하고 구조·글리프·부호 규칙만 여기서 강제한다.
export default function ChangeChip({ value, className = 'wl__change' }) {
  const dir = changeDir(value) // 결측=null → 클래스 없음(회색)·글리프 ─
  return (
    <span className={`${className} ${dir ?? ''}`}>
      <span aria-hidden="true">{dirGlyph(dir)}</span> {signedNum(value)}%
    </span>
  )
}
