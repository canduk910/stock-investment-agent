// 챗봇 진행 단계 체크리스트(W09 SSE). 백엔드 stage 이벤트(analyze|regime|generate|summarize)와
// 단일 출처. 현재 stage 를 받아 각 단계의 status(done/active/pending)를 계산하는 순수 로직.
// 렌더(ChatMessage)는 이 status→CSS 클래스 매핑만 담당한다.

// 단계 순서·라벨(백엔드 stage 키와 일치). summarize 는 tool_calls 답변에서만 등장하지만,
// 체크리스트에는 항상 표시하고 도달 전엔 pending(대기)으로 흐리게 둔다.
export const STAGES = [
  { key: 'analyze', label: '질문 분석' },
  { key: 'regime', label: '시장 국면 조회' },
  { key: 'generate', label: '답변 작성 중' },
  { key: 'summarize', label: '정리 중' },
]

// 현재 stage → [{key, label, status}]. current 이전=done(✓), current=active(●), 이후=pending.
// 미지/결측 current 는 첫 단계 진행으로 방어(빈 리스트·크래시 금지).
export function stageChecklist(current) {
  let idx = STAGES.findIndex((s) => s.key === current)
  if (idx < 0) idx = 0
  return STAGES.map((s, i) => ({
    key: s.key,
    label: s.label,
    status: i < idx ? 'done' : i === idx ? 'active' : 'pending',
  }))
}
