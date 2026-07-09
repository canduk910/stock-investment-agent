import { routePopups } from '../lib/popupRouter.js'
import { stageChecklist } from '../lib/chatStages.js'

// 팝업 kind → 재열기 칩 라벨(닫은 팝업을 다시 열 수 있게).
const POPUP_CHIP_LABEL = {
  stock_report: '종목 리포트',
  macro_dashboard: '시장 국면',
  watchlist: '관심종목',
}

// 진행 단계 체크리스트(SSE 스트리밍 중, 아직 토큰이 오기 전) — 완료✓·현재●·대기.
// status→CSS 클래스는 chatStages(순수 로직)가 계산한 값을 그대로 매핑한다(색은 theme.css 토큰).
function ChatStages({ stage }) {
  const list = stageChecklist(stage)
  return (
    <ul className="chat__stages" aria-label="진행 단계">
      {list.map((s) => (
        <li key={s.key} className={`chat__stage chat__stage--${s.status}`}>
          <span className="chat__stage-mark" aria-hidden="true">
            {s.status === 'done' ? '✓' : s.status === 'active' ? '●' : '○'}
          </span>
          <span className="chat__stage-label">{s.label}</span>
        </li>
      ))}
    </ul>
  )
}

// 단일 말풍선 — role 별 정렬/색. 사용자=우측(파랑 soft), 봇=좌측(흰 표면).
// 봇 응답에 popups 가 있으면 아래에 "다시 열기" 칩을 둔다(라우팅 계약 재사용, 닫아도 재접근 가능).
// text 는 LLM 서술이라 줄바꿈 보존(pre-wrap, CSS). 색은 theme.css 토큰만.
//
// 스트리밍(streaming=true): 아직 토큰 전(text 비어있음)이면 진행 단계 체크리스트를 보여주고,
// 토큰이 들어오면 라이브 타이핑 텍스트 + 깜빡이는 커서를 붙인다. 완료 시 streaming=false 로
// 커서·체크리스트가 사라지고 최종 텍스트 + 팝업 칩만 남는다(무한 스피너 금지).
export default function ChatMessage({ role, text, popups, streaming, stage, onOpenPopup }) {
  const isUser = role === 'user'
  const specs = !isUser ? routePopups(popups) : []
  const showStages = streaming && !text // 토큰 도착 전: 단계 체크리스트
  return (
    <div className={`chat__row ${isUser ? 'chat__row--user' : 'chat__row--bot'}`}>
      <div className={`chat__bubble ${isUser ? 'chat__bubble--user' : 'chat__bubble--bot'}`}>
        {showStages && <ChatStages stage={stage} />}
        {text ? (
          <span className="chat__text">
            {text}
            {streaming && <span className="chat__cursor" aria-hidden="true" />}
          </span>
        ) : null}
        {specs.length > 0 && (
          <div className="chat__popup-chips">
            {specs.map((spec, i) => (
              <button
                key={i}
                type="button"
                className="chat__popup-chip"
                onClick={() => onOpenPopup(spec)}
              >
                {POPUP_CHIP_LABEL[spec.kind] ?? '자세히'} 열기
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
