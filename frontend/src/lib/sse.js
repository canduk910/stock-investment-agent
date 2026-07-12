// 제네릭 SSE 리더 — 챗 외 SSE(리포트 진행 스트림 등) 소비용. 순수 프레임 파서
// `parseSSEBuffer`(sseChat.js, 이미 테스트됨)를 재사용하고, getReader/TextDecoder 루프만 담당한다.
// POST+body SSE 라 EventSource 대신 fetch 스트림 리더를 쓴다(챗과 동일 패턴).
import { parseSSEBuffer } from './sseChat.js'

// fetch Response(text/event-stream)를 받아 각 이벤트 객체를 onEvent(ev)로 디스패치.
// ok=false/body 없음 → onError(무한 대기 금지). 멀티바이트 경계는 TextDecoder(stream:true)로 방어.
export async function readSSE(response, onEvent, onError) {
  if (!response || !response.ok || !response.body) {
    onError?.(new Error(`stream ${response?.status ?? 'no-body'}`))
    return
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  try {
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const { events, rest } = parseSSEBuffer(buffer)
      buffer = rest
      for (const ev of events) onEvent?.(ev)
    }
    // 종료 후 남은 완성 프레임 flush.
    buffer += decoder.decode()
    if (buffer) {
      const { events } = parseSSEBuffer(buffer + '\n\n')
      for (const ev of events) onEvent?.(ev)
    }
  } catch (e) {
    onError?.(e)
  }
}
