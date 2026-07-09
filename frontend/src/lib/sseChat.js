// SSE 챗 스트림 파싱·리딩(W09). 백엔드 POST /api/chat/stream 은 text/event-stream 으로
// 이벤트를 흘린다. fetch + ReadableStream 리더로 받아 `data: {json}\n\n` 프레임을 재조립한다
// (POST+body 라 EventSource 대신 fetch 스트림을 쓴다).
//
// 이벤트 계약(백엔드와 단일 출처, 승인 계획 §SSE 이벤트 계약):
//   {"type":"stage","stage":"analyze|regime|generate|summarize"}
//   {"type":"token","text":"…"}
//   {"type":"popups","popups":[{name,args}]}
//   {"type":"done","popups":[…]}
//
// 파싱(parseSSEBuffer)은 순수함수로 분리해 테스트 가능하게 하고, 리딩(readChatStream)은
// getReader 루프 + TextDecoder(stream:true, 멀티바이트 경계 방어)만 담당한다.

// 누적 문자열에서 완성된(\n\n 경계) data: 이벤트를 파싱해 { events, rest } 로 반환한다.
// 미완성 마지막 프레임은 rest 로 남겨 다음 청크와 이어붙인다(청크가 이벤트 경계를 가로지름).
// data: 가 아닌 라인(주석 ':', keep-alive 등)은 무시하고, 깨진 JSON 은 조용히 건너뛴다.
export function parseSSEBuffer(buffer) {
  const events = []
  // \n\n 로 프레임 분리. 마지막 조각은 경계가 아직 안 온 잔여이므로 rest 로 보류한다.
  const parts = buffer.split('\n\n')
  const rest = parts.pop() // 항상 존재(완성 버퍼면 '')
  for (const frame of parts) {
    for (const line of frame.split('\n')) {
      if (!line.startsWith('data:')) continue
      const payload = line.slice(5).trim()
      if (!payload) continue
      try {
        events.push(JSON.parse(payload))
      } catch {
        // 깨진 프레임은 무시(부분 수신 아님 — 경계로 잘린 완성 프레임이므로 서버측 결함). 크래시 금지.
      }
    }
  }
  return { events, rest }
}

// 이벤트 하나를 type 별 핸들러로 디스패치. 핸들러는 모두 선택적(누락해도 크래시 금지).
// done 을 실제로 디스패치했으면 true 반환(끊긴 스트림 판별용).
function dispatch(ev, handlers) {
  switch (ev.type) {
    case 'stage':
      handlers.onStage?.(ev.stage)
      break
    case 'token':
      handlers.onToken?.(ev.text ?? '')
      break
    case 'popups':
      handlers.onPopups?.(ev.popups ?? [])
      break
    case 'done':
      handlers.onDone?.(ev.popups ?? [])
      return true
    default:
      break // 미지 type 은 조용히 무시(전방 호환)
  }
  return false
}

// response.body.getReader() 루프. 청크를 TextDecoder(stream:true)로 디코드해 버퍼에 누적하고
// parseSSEBuffer 로 완성 이벤트를 뽑아 디스패치한다. ok=false/body 없음 → onError(무한 대기 금지).
export async function readChatStream(response, handlers = {}) {
  if (!response || !response.ok || !response.body) {
    handlers.onError?.(new Error(`stream ${response?.status ?? 'no-body'}`))
    return
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let gotDone = false
  try {
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const { events, rest } = parseSSEBuffer(buffer)
      buffer = rest
      for (const ev of events) if (dispatch(ev, handlers)) gotDone = true
    }
    // 스트림 종료 후 남은 완성 프레임 처리(마지막 flush).
    buffer += decoder.decode()
    if (buffer) {
      const { events } = parseSSEBuffer(buffer + '\n\n')
      for (const ev of events) if (dispatch(ev, handlers)) gotDone = true
    }
    // done 없이 스트림이 끝남 = 끊긴 응답. onError 로 폴백 유도(무한 스피너 금지).
    if (!gotDone) handlers.onError?.(new Error('stream ended without done'))
  } catch (e) {
    handlers.onError?.(e)
  }
}
