import { describe, it, expect, vi } from 'vitest'
import { parseSSEBuffer, readChatStream } from './sseChat.js'

// 계약 근거(승인 계획 §SSE 이벤트 계약 · Task #14): 백엔드가 흘리는 이벤트는
//   {"type":"stage","stage":"analyze|regime|generate|summarize"}
//   {"type":"token","text":"…"}
//   {"type":"popups","popups":[{name,args}]}
//   {"type":"done","popups":[…]}
// 각 이벤트는 `data: {json}\n\n` 프레임으로 온다. parseSSEBuffer 는 누적 문자열에서
// 완성된(\n\n 경계) data: 이벤트만 파싱해 배열로 내고, 미완성 잔여는 버퍼로 남긴다(순수함수).
// fetch 스트림 청크는 이벤트 경계를 임의로 가로질러 쪼개지므로 이 재조립이 핵심이다.

describe('parseSSEBuffer — SSE data 프레임 재조립(순수함수)', () => {
  it('완성된 단일 이벤트 → 파싱된 배열 + 빈 잔여', () => {
    const buf = 'data: {"type":"stage","stage":"analyze"}\n\n'
    const { events, rest } = parseSSEBuffer(buf)
    expect(events).toEqual([{ type: 'stage', stage: 'analyze' }])
    expect(rest).toBe('')
  })

  it('한 청크에 여러 이벤트가 붙어 옴 → 순서대로 모두 파싱', () => {
    const buf =
      'data: {"type":"stage","stage":"generate"}\n\n' +
      'data: {"type":"token","text":"삼"}\n\n' +
      'data: {"type":"token","text":"성"}\n\n'
    const { events, rest } = parseSSEBuffer(buf)
    expect(events).toEqual([
      { type: 'stage', stage: 'generate' },
      { type: 'token', text: '삼' },
      { type: 'token', text: '성' },
    ])
    expect(rest).toBe('')
  })

  it('이벤트 경계를 가로질러 미완성으로 끝남 → 완성분만 내고 잔여 버퍼 보존', () => {
    const buf =
      'data: {"type":"token","text":"안"}\n\n' + 'data: {"type":"token","text":"녕'
    const { events, rest } = parseSSEBuffer(buf)
    expect(events).toEqual([{ type: 'token', text: '안' }])
    expect(rest).toBe('data: {"type":"token","text":"녕')
  })

  it('완성된 이벤트가 없음(잔여만) → 빈 배열 + 원본 버퍼 유지', () => {
    const buf = 'data: {"type":"stage","stage'
    const { events, rest } = parseSSEBuffer(buf)
    expect(events).toEqual([])
    expect(rest).toBe(buf)
  })

  it('popups/done 이벤트도 배열/객체 필드까지 파싱', () => {
    const buf =
      'data: {"type":"popups","popups":[{"name":"show_stock_report","args":{"ticker":"005930"}}]}\n\n' +
      'data: {"type":"done","popups":[{"name":"show_stock_report","args":{"ticker":"005930"}}]}\n\n'
    const { events } = parseSSEBuffer(buf)
    expect(events[0]).toEqual({
      type: 'popups',
      popups: [{ name: 'show_stock_report', args: { ticker: '005930' } }],
    })
    expect(events[1].type).toBe('done')
    expect(events[1].popups[0].name).toBe('show_stock_report')
  })

  it('빈 keep-alive 라인·비 data 라인은 무시하고 data 만 파싱', () => {
    const buf = ': keep-alive\n\ndata: {"type":"stage","stage":"regime"}\n\n'
    const { events, rest } = parseSSEBuffer(buf)
    expect(events).toEqual([{ type: 'stage', stage: 'regime' }])
    expect(rest).toBe('')
  })

  it('깨진 JSON 프레임은 조용히 건너뛴다(크래시 금지)', () => {
    const buf =
      'data: {oops not json}\n\n' + 'data: {"type":"token","text":"ok"}\n\n'
    const { events } = parseSSEBuffer(buf)
    expect(events).toEqual([{ type: 'token', text: 'ok' }])
  })
})

// readChatStream: response.body.getReader() 를 돌며 청크를 TextDecoder 로 디코드하고
// parseSSEBuffer 로 재조립해 type 별 핸들러로 디스패치한다. 청크 경계를 가로지르는 이벤트,
// 한글 멀티바이트 경계에서 쪼개진 UTF-8 바이트를 방어한다(stream:true 디코딩).

// getReader() 를 흉내내는 헬퍼 — chunks(Uint8Array 배열)를 순서대로 반환.
function makeResponse(chunks) {
  let i = 0
  return {
    ok: true,
    body: {
      getReader() {
        return {
          read() {
            if (i < chunks.length) {
              return Promise.resolve({ value: chunks[i++], done: false })
            }
            return Promise.resolve({ value: undefined, done: true })
          },
        }
      },
    },
  }
}

const enc = (s) => new TextEncoder().encode(s)

describe('readChatStream — 리더 루프 + 핸들러 디스패치', () => {
  it('stage/token/popups/done 을 각 핸들러로 순서대로 디스패치', async () => {
    const res = makeResponse([
      enc('data: {"type":"stage","stage":"analyze"}\n\n'),
      enc('data: {"type":"token","text":"안녕"}\n\n'),
      enc('data: {"type":"popups","popups":[{"name":"show_macro_dashboard","args":{}}]}\n\n'),
      enc('data: {"type":"done","popups":[{"name":"show_macro_dashboard","args":{}}]}\n\n'),
    ])
    const onStage = vi.fn()
    const onToken = vi.fn()
    const onPopups = vi.fn()
    const onDone = vi.fn()
    await readChatStream(res, { onStage, onToken, onPopups, onDone })
    expect(onStage).toHaveBeenCalledWith('analyze')
    expect(onToken).toHaveBeenCalledWith('안녕')
    expect(onPopups).toHaveBeenCalledWith([{ name: 'show_macro_dashboard', args: {} }])
    expect(onDone).toHaveBeenCalledWith([{ name: 'show_macro_dashboard', args: {} }])
  })

  it('이벤트가 청크 경계를 가로질러 쪼개져 와도 올바르게 재조립', async () => {
    const res = makeResponse([
      enc('data: {"type":"sta'),
      enc('ge","stage":"generate"}\n\n' + 'data: {"type":"to'),
      enc('ken","text":"완료"}\n\n'),
    ])
    const onStage = vi.fn()
    const onToken = vi.fn()
    await readChatStream(res, { onStage, onToken, onDone: vi.fn() })
    expect(onStage).toHaveBeenCalledWith('generate')
    expect(onToken).toHaveBeenCalledWith('완료')
  })

  it('한글 UTF-8 바이트가 청크 경계에서 쪼개져도 손상 없이 디코드(stream:true)', async () => {
    // "가" = EA B0 80 (3바이트). 프레임을 바이트 단위로 두 청크로 분할.
    const full = 'data: {"type":"token","text":"가"}\n\n'
    const bytes = enc(full)
    const mid = 30 // "가"의 멀티바이트 중간을 가르는 지점
    const res = makeResponse([bytes.slice(0, mid), bytes.slice(mid)])
    const onToken = vi.fn()
    await readChatStream(res, { onToken, onDone: vi.fn() })
    expect(onToken).toHaveBeenCalledWith('가')
  })

  it('response.ok=false 또는 body 없음 → onError 호출(무한 대기 금지)', async () => {
    const onError = vi.fn()
    await readChatStream({ ok: false, status: 500 }, { onError })
    expect(onError).toHaveBeenCalled()
  })

  it('핸들러 누락(선택적)이어도 크래시하지 않는다', async () => {
    const res = makeResponse([enc('data: {"type":"token","text":"x"}\n\n')])
    await expect(readChatStream(res, {})).resolves.toBeUndefined()
  })

  it('done 이벤트 없이 스트림이 끝나면 onError(끊긴 스트림 → 무한 스피너 금지)', async () => {
    // 토큰만 오고 done 없이 리더가 done:true → 응답 미완성. onDone 은 호출되지 않아야 하고
    // onError 로 폴백을 유도한다(loading 이 영원히 true 로 남는 것 방지).
    const res = makeResponse([enc('data: {"type":"token","text":"부분"}\n\n')])
    const onDone = vi.fn()
    const onError = vi.fn()
    await readChatStream(res, { onToken: vi.fn(), onDone, onError })
    expect(onDone).not.toHaveBeenCalled()
    expect(onError).toHaveBeenCalled()
  })

  it('done 을 정상 수신하면 onError 는 호출되지 않는다', async () => {
    const res = makeResponse([
      enc('data: {"type":"token","text":"ok"}\n\n'),
      enc('data: {"type":"done","popups":[]}\n\n'),
    ])
    const onDone = vi.fn()
    const onError = vi.fn()
    await readChatStream(res, { onToken: vi.fn(), onDone, onError })
    expect(onDone).toHaveBeenCalledWith([])
    expect(onError).not.toHaveBeenCalled()
  })
})
