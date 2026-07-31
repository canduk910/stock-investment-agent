import { useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { routePopups } from '../lib/popupRouter.js'
import { stageChecklist } from '../lib/chatStages.js'
import MermaidDiagram from './MermaidDiagram.jsx'

// 코드블록 렌더러 — react-markdown v9 는 펜스 코드를 <pre><code class="language-xxx"> 로 낸다.
// pre 만 오버라이드하면 인라인 code 경로는 안 건드려 기존 .chat__md code(인라인) 계약이 그대로 보존된다.
// language-mermaid 펜스만 MermaidDiagram 으로, 나머지 코드블록은 기본 <pre> 로 렌더.
// (node 는 DOM 속성이 아니라 destructure 로 제거 — <pre> 에 새지 않게.)
function MarkdownPre({ node, children, streaming, ...props }) {
  const codeNode = node?.children?.[0]
  const className = codeNode?.properties?.className
  const isMermaid = Array.isArray(className) && className.includes('language-mermaid')
  if (isMermaid) {
    const raw = codeNode?.children?.[0]?.value ?? ''
    return <MermaidDiagram chart={raw} streaming={streaming} />
  }
  return <pre {...props}>{children}</pre>
}

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
  // 마크다운 컴포넌트 매핑 — pre 렌더러가 streaming 을 클로저로 잡아야 해 컴포넌트 내부에서 memo.
  // 스트리밍 중엔 streaming=true 로 고정(토큰 누적)이라 재생성 없음, 완료 시 false 로 1회만 재생성.
  const mdComponents = useMemo(
    () => ({
      // 링크는 새 탭 + 보안 rel. react-markdown 기본이 원문 HTML 미렌더 → <script> 등 문자 이스케이프(XSS 불가).
      a: ({ node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
      pre: (props) => <MarkdownPre {...props} streaming={streaming} />,
    }),
    [streaming],
  )
  return (
    <div className={`chat__row ${isUser ? 'chat__row--user' : 'chat__row--bot'}`}>
      <div className={`chat__bubble ${isUser ? 'chat__bubble--user' : 'chat__bubble--bot'}`}>
        {showStages && <ChatStages stage={stage} />}
        {text ? (
          isUser ? (
            // 사용자 입력은 평문(줄바꿈 보존) — 사용자가 친 문자 그대로.
            <span className="chat__text">{text}</span>
          ) : (
            // 봇(LLM) 응답은 마크다운 렌더 — 굵게/목록/코드/제목/링크 등. 스트리밍 중엔 커서 병기
            // (미완성 문법은 닫힐 때까지 평문으로 보이다가 완성되면 렌더). 원문 HTML은 미렌더(XSS 불가).
            <div className="chat__md">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                {text}
              </ReactMarkdown>
              {streaming && <span className="chat__cursor" aria-hidden="true" />}
            </div>
          )
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
