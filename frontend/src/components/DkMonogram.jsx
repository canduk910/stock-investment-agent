// DK 모노그램 CI(공용) — 남색 스퀘어(rx) + 우상단 주황 마름모 + 중앙 흰 "DK". 색은 theme.css 토큰.
// 톱바(App)·로그인 화면(LoginScreen)이 공유하는 브랜드 마크 단일 출처 → CI 일관(주황 마름모 포함).
// size 로 크기 조절(내부 좌표는 34 단위 viewBox 로 스케일). 기본 className=app__monogram(display:block).
export default function DkMonogram({ size = 34, className = 'app__monogram' }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 34 34"
      role="img"
      aria-label="디케이 투자에이전트 로고"
    >
      <rect x="0" y="0" width="34" height="34" rx="9" fill="var(--c-navy)" />
      <rect
        x="24.5"
        y="3.5"
        width="6"
        height="6"
        rx="1"
        fill="var(--c-emph)"
        transform="rotate(45 27.5 6.5)"
      />
      <text
        x="17"
        y="17"
        textAnchor="middle"
        dominantBaseline="central"
        fill="var(--c-white)"
        fontSize="13.5"
        fontWeight="900"
        letterSpacing="0.5"
      >
        DK
      </text>
    </svg>
  )
}
