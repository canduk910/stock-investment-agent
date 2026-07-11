import { useEffect, useRef, useState } from 'react'
import { postChat, postChatStream } from '../api.js'
import { routePopups } from '../lib/popupRouter.js'
import ChatMessage from './ChatMessage.jsx'

// 챗봇 패널(W09→UX 개편) — 자연어 질문 → {text, popups}. text 는 말풍선, popups 는 우측 패널 트리거.
// 세션: 마운트 시 crypto.randomUUID 1회 → 서버가 히스토리 보관(프론트는 id+메시지만 전송).
// UX 개편: 팝업 모달 폐기. 응답의 popups 는 onShowPanel(routePopups[0])로 우측 RightPanel 에 인라인 렌더한다
//   — LLM 은 "무엇을 띄울지"만 주고, 팝업 실데이터는 우측 컴포넌트가 API 로 직접 조회(환각 차단).
// 색은 theme.css 토큰만. 하단 면책 고지 상시(면허 있는 자문 아님).

const DISCLAIMER =
  '본 챗봇은 정보 제공 목적이며 투자 자문·매매 권유가 아닙니다. 판정·수치는 코드가 결정하고 ' +
  '설명만 AI 가 돕습니다. 투자 판단과 그 결과의 책임은 전적으로 본인에게 있습니다(면허 있는 투자자문 아님).'

// 빈 상태 제안 칩 — 클릭 시 그대로 전송(온보딩). 국면/종목/잔고/워치리스트 편집을 한 번씩 예시.
const SUGGESTIONS = [
  '지금 시장 어때?',
  '삼성전자 어때?',
  '내 잔고 보여줘',
  '카카오 목표가 4만원으로 바꿔줘',
]

export default function ChatPanel({ sessionId: sessionIdProp, onShowPanel, consult, onEndConsult }) {
  // 세션 id 는 App 이 단일 소유(리포트 상담 컨텍스트와 공유). prop 미전달 시(구 테스트) 자체 생성 폴백.
  const sessionRef = useRef(null)
  if (sessionRef.current === null) {
    sessionRef.current =
      sessionIdProp ??
      (typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : `sess-${Date.now()}-${Math.random().toString(16).slice(2)}`)
  }
  // prop 이 뒤늦게(또는 바뀌어) 오면 그것을 우선(App 세션과 일치 보장).
  const sessionId = { current: sessionIdProp ?? sessionRef.current }

  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const lastQueryRef = useRef(null)
  const listRef = useRef(null)

  // 응답 popups → 우측 패널 spec 으로 리프팅(모달 폐기). 첫 spec 을 우측에 인라인 렌더.
  //   과거 팝업 재열기 칩(ChatMessage.onOpenPopup)도 같은 경로로 우측 패널에 다시 띄운다.
  function showPanel(specs) {
    if (specs.length && onShowPanel) onShowPanel(specs[0])
  }

  // 새 메시지·로딩 변화 시 맨 아래로 스크롤(토큰 타이핑 중 messages 갱신마다 하단 유지).
  useEffect(() => {
    const el = listRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, loading])

  // 마지막(진행 중) 봇 placeholder 만 부분 갱신하는 헬퍼. patch 가 함수면 이전 봇 메시지를 받아
  // 갱신 객체를 돌려준다(토큰 누적 text += t 처럼 이전 값이 필요한 경우). 객체면 그대로 병합.
  function patchLastBot(patch) {
    setMessages((m) => {
      if (m.length === 0) return m
      const last = m[m.length - 1]
      if (last.role !== 'bot' || !last.streaming) return m
      const next = typeof patch === 'function' ? patch(last) : patch
      return [...m.slice(0, -1), { ...last, ...next }]
    })
  }

  // 스트림 done — 봇 메시지 확정(streaming 종료). 우측 패널 전환은 이미 onPopups 에서(설명보다 먼저)
  //   처리했으므로 여기선 다시 띄우지 않는다 — 끝에서 재전환하면 스트리밍 중 사용자가 옮긴 탭을 되돌린다.
  function finishStream(popups) {
    const specs = routePopups(popups)
    setMessages((m) => {
      if (m.length === 0) return m
      const last = m[m.length - 1]
      if (last.role !== 'bot' || !last.streaming) return m
      const text =
        (last.text && last.text.trim()) ||
        (specs.length ? '요청하신 내용을 우측 패널에 열었습니다.' : '')
      return [...m.slice(0, -1), { ...last, text, popups, streaming: false }]
    })
    setLoading(false)
  }

  // 논스트림 폴백(스트림 실패 시 1회) — 기존 postChat 경로. 봇 placeholder 를 결과로 대체한다.
  async function runChatFallback(query) {
    try {
      const res = await postChat(sessionId.current, query)
      const specs = routePopups(res.popups)
      const text =
        (res.text && res.text.trim()) ||
        (specs.length ? '요청하신 내용을 우측 패널에 열었습니다.' : '')
      // 진행 중 placeholder 가 있으면 교체, 없으면 append.
      setMessages((m) => {
        const last = m[m.length - 1]
        const bot = { role: 'bot', text, popups: res.popups ?? [], streaming: false }
        return last && last.role === 'bot' && last.streaming
          ? [...m.slice(0, -1), bot]
          : [...m, bot]
      })
      showPanel(specs)
      setError(null)
    } catch (e) {
      // 폴백도 실패 → 배너 + 재시도. 진행 중 placeholder 는 제거(무한 스피너 금지).
      setMessages((m) => {
        const last = m[m.length - 1]
        return last && last.role === 'bot' && last.streaming ? m.slice(0, -1) : m
      })
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  // 실제 호출(사용자 버블 추가 없이) — 최초 전송/재시도 공통 경로. SSE 스트리밍이 기본.
  async function runChat(query) {
    setLoading(true)
    setError(null)
    // 봇 placeholder push — 이후 stage/token 이벤트가 이 메시지를 라이브 갱신한다.
    setMessages((m) => [
      ...m,
      { role: 'bot', text: '', streaming: true, stage: 'analyze', popups: [] },
    ])
    let fellBack = false
    await postChatStream(sessionId.current, query, {
      onStage: (stage) => patchLastBot({ stage }),
      onToken: (t) => patchLastBot((last) => ({ text: last.text + t })), // 라이브 타이핑 누적
      onPopups: (popups) => {
        // 팝업 지시(tool_call)는 설명 narration 토큰보다 먼저 도착한다(백엔드 chat_stream 순서:
        //   popups → summarize → token…). 도착 즉시 우측 패널을 전환해 "패널 먼저, 설명은 이어서"
        //   흐름을 만든다(전엔 onDone 에서만 전환해 응답이 끝난 뒤 패널이 바뀌었다).
        patchLastBot({ popups })
        showPanel(routePopups(popups))
      },
      onDone: (popups) => finishStream(popups),
      onError: () => {
        // 스트림 실패 → 논스트림 폴백 1회(무한 스피너 금지). 중복 폴백 방지.
        if (fellBack) return
        fellBack = true
        runChatFallback(query)
      },
    })
  }

  // 사용자 질의 전송 공통 경로 — 폼 제출·제안 칩이 공유. 사용자 버블 push 후 runChat.
  function submitQuery(q) {
    const query = q.trim()
    if (!query || loading) return
    setMessages((m) => [...m, { role: 'user', text: query }])
    setInput('')
    lastQueryRef.current = query
    runChat(query)
  }

  function send(e) {
    e.preventDefault()
    submitQuery(input)
  }

  function retry() {
    if (lastQueryRef.current && !loading) runChat(lastQueryRef.current)
  }

  return (
    <section className="chat" aria-label="투자 챗봇">
      <header className="dashboard__header">
        <div>
          <h1>투자 챗봇</h1>
          <p className="dashboard__subtitle">
            자연어로 물어보세요 · 판정·수치는 코드가 결정(LLM 미개입), 팝업 데이터는 실시간 직접 조회
          </p>
        </div>
      </header>

      <div className="chat__panel">
        {consult ? (
          <div className="banner banner--emph chat__consult" role="status">
            <span className="chat__consult-text">
              {consult.broker ? `${consult.broker} ` : ''}리포트를 상담 컨텍스트로 불러왔어요 — 이
              리포트를 근거로 이어서 물어보세요.
            </span>
            <button
              type="button"
              className="banner__retry"
              onClick={() => onEndConsult?.()}
              aria-label="리포트 상담 종료"
            >
              상담 종료
            </button>
          </div>
        ) : null}

        <div className="chat__messages" ref={listRef} role="log" aria-live="polite">
          {messages.length === 0 ? (
            <div className="chat__empty">
              <p className="chat__empty-title">이렇게 물어보세요</p>
              <div className="chat__suggest">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    className="chat__suggest-chip"
                    onClick={() => submitQuery(s)}
                    disabled={loading}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((msg, i) => (
              <ChatMessage
                key={i}
                role={msg.role}
                text={msg.text}
                popups={msg.popups}
                streaming={msg.streaming}
                stage={msg.stage}
                onOpenPopup={(spec) => onShowPanel?.(spec)}
              />
            ))
          )}
        </div>

        {error && (
          <div className="banner banner--warn chat__error" role="status">
            응답을 가져오지 못했습니다({error}).
            <button type="button" className="banner__retry" onClick={retry} disabled={loading}>
              ↻ 재시도
            </button>
          </div>
        )}

        <form className="chat__form" onSubmit={send} autoComplete="off">
          <input
            className="chat__input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="메시지를 입력하세요"
            aria-label="챗봇 메시지 입력"
            disabled={loading}
          />
          <button className="refresh chat__send" type="submit" disabled={loading || !input.trim()}>
            {loading ? '전송 중…' : '전송'}
          </button>
        </form>
      </div>

      <p className="chat__disclaimer" role="note">
        {DISCLAIMER}
      </p>
    </section>
  )
}
