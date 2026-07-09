import { useEffect, useRef, useState } from 'react'
import { postChat, postChatStream } from '../api.js'
import { routePopups } from '../lib/popupRouter.js'
import ChatMessage from './ChatMessage.jsx'
import Modal from './Modal.jsx'
import PopupStockReport from './PopupStockReport.jsx'
import PopupWatchlist from './PopupWatchlist.jsx'
import RegimeGauge from './RegimeGauge.jsx'

// 챗봇 패널(W09) — 자연어 질문 → {text, popups}. text 는 말풍선, popups 는 팝업 모달 트리거.
// 세션: 마운트 시 crypto.randomUUID 1회 → 서버가 히스토리 보관(프론트는 id+메시지만 전송).
// 팝업 실데이터는 프론트가 직접 조회(환각 차단): show_stock_report→PopupStockReport(fetchStockBundle),
//   show_macro_dashboard→RegimeGauge(fetchMacroRegime, 자체 조회·무캐시), show_watchlist→W10 플레이스홀더.
// 색은 theme.css 토큰만. 하단 면책 고지 상시(면허 있는 자문 아님).

const POPUP_TITLE = {
  stock_report: '종목 종합리포트',
  macro_dashboard: '시장 국면 대시보드',
  watchlist: '관심종목',
}

const DISCLAIMER =
  '본 챗봇은 정보 제공 목적이며 투자 자문·매매 권유가 아닙니다. 판정·수치는 코드가 결정하고 ' +
  '설명만 AI 가 돕습니다. 투자 판단과 그 결과의 책임은 전적으로 본인에게 있습니다(면허 있는 투자자문 아님).'

// 팝업 스펙(kind) → 모달 본문. 데이터는 각 컴포넌트가 직접 조회한다.
// stock_report 는 ticker 형식(6자리 숫자)이 불량이면 조회하지 않고 안내만 한다(잘못된 백엔드 조회 방지).
function PopupBody({ spec }) {
  switch (spec.kind) {
    case 'stock_report':
      if (!spec.valid) {
        return (
          <div className="popup__state">
            종목 코드를 인식하지 못했어요. 종목명이나 6자리 코드(예: 005930)로 다시 물어봐 주세요.
          </div>
        )
      }
      return <PopupStockReport ticker={spec.args.ticker} stockName={spec.args.stock_name} />
    case 'macro_dashboard':
      return <RegimeGauge />
    case 'watchlist':
      return <PopupWatchlist args={spec.args} />
    default:
      return null
  }
}

export default function ChatPanel() {
  const sessionId = useRef(null)
  if (sessionId.current === null) {
    // 마운트 시 1회 생성(구형 브라우저 폴백 포함).
    sessionId.current =
      typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : `sess-${Date.now()}-${Math.random().toString(16).slice(2)}`
  }

  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [popupQueue, setPopupQueue] = useState([]) // 열려 있는 팝업 스택(닫으면 다음)
  const lastQueryRef = useRef(null)
  const listRef = useRef(null)

  const activePopup = popupQueue[0] ?? null

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

  // 스트림 done — 최종 popups 확정 → 라우팅해 모달 오픈(현행 동작 그대로). text 가 비면 폴백 문구.
  function finishStream(popups) {
    const specs = routePopups(popups)
    setMessages((m) => {
      if (m.length === 0) return m
      const last = m[m.length - 1]
      if (last.role !== 'bot' || !last.streaming) return m
      const text =
        (last.text && last.text.trim()) ||
        (specs.length ? '요청하신 내용을 팝업으로 열었습니다.' : '')
      return [...m.slice(0, -1), { ...last, text, popups, streaming: false }]
    })
    if (specs.length) setPopupQueue(specs) // 자동으로 팝업 오픈
    setLoading(false)
  }

  // 논스트림 폴백(스트림 실패 시 1회) — 기존 postChat 경로. 봇 placeholder 를 결과로 대체한다.
  async function runChatFallback(query) {
    try {
      const res = await postChat(sessionId.current, query)
      const specs = routePopups(res.popups)
      const text =
        (res.text && res.text.trim()) ||
        (specs.length ? '요청하신 내용을 팝업으로 열었습니다.' : '')
      // 진행 중 placeholder 가 있으면 교체, 없으면 append.
      setMessages((m) => {
        const last = m[m.length - 1]
        const bot = { role: 'bot', text, popups: res.popups ?? [], streaming: false }
        return last && last.role === 'bot' && last.streaming
          ? [...m.slice(0, -1), bot]
          : [...m, bot]
      })
      if (specs.length) setPopupQueue(specs)
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
      onPopups: (popups) => patchLastBot({ popups }),
      onDone: (popups) => finishStream(popups),
      onError: () => {
        // 스트림 실패 → 논스트림 폴백 1회(무한 스피너 금지). 중복 폴백 방지.
        if (fellBack) return
        fellBack = true
        runChatFallback(query)
      },
    })
  }

  function send(e) {
    e.preventDefault()
    const q = input.trim()
    if (!q || loading) return
    setMessages((m) => [...m, { role: 'user', text: q }])
    setInput('')
    lastQueryRef.current = q
    runChat(q)
  }

  function retry() {
    if (lastQueryRef.current && !loading) runChat(lastQueryRef.current)
  }

  function closePopup() {
    setPopupQueue((q) => q.slice(1))
  }

  return (
    <section className="dashboard chat" aria-label="투자 챗봇">
      <header className="dashboard__header">
        <div>
          <h1>투자 챗봇</h1>
          <p className="dashboard__subtitle">
            자연어로 물어보세요 · 판정·수치는 코드가 결정(LLM 미개입), 팝업 데이터는 실시간 직접 조회
          </p>
        </div>
      </header>

      <div className="chat__panel">
        <div className="chat__messages" ref={listRef} role="log" aria-live="polite">
          {messages.length === 0 ? (
            <div className="chat__empty">
              예: “지금 시장 어때?” · “삼성전자 어때?” · “PER이 뭐야?”
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
                onOpenPopup={(spec) => setPopupQueue([spec])}
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

      {activePopup && (
        <Modal
          title={
            activePopup.kind === 'stock_report' && activePopup.args.stock_name
              ? `${activePopup.args.stock_name} · ${POPUP_TITLE.stock_report}`
              : POPUP_TITLE[activePopup.kind] ?? '팝업'
          }
          onClose={closePopup}
        >
          <PopupBody spec={activePopup} />
        </Modal>
      )}
    </section>
  )
}
