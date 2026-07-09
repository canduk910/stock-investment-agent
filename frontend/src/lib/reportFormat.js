// AI 리포트 표현 매핑(순수) — 종합의견 → 배지 톤. 색 자체는 컴포넌트가 theme.css 토큰으로 매핑한다.
// 계약: 종합의견은 Pydantic StockReport Literal["긍정적","중립","신중"](llm-engineer SSOT)만 유효.
//   매수/매도 등 명령형 라벨은 스키마가 원천 배제한다 → 프론트도 알 수 없는 값은 중립(muted)으로 방어.
//   톤 규칙: 긍정적=up(파랑) / 중립=muted(회색) / 신중=emph(주황, 강조 — 위험 아님이므로 빨강 아님).

export const OPINION_LABELS = {
  긍정적: '긍정적',
  중립: '중립',
  신중: '신중',
}

const OPINION_TONE = {
  긍정적: 'up',
  중립: 'muted',
  신중: 'emph',
}

// 종합의견 문자열 → 배지 톤('up' | 'muted' | 'emph'). 미지/결측은 'muted'(임의 색 금지).
export function opinionTone(opinion) {
  return OPINION_TONE[opinion] ?? 'muted'
}
