import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  clampChatWidth,
  loadChatWidth,
  saveChatWidth,
  CHAT_MIN,
  RIGHT_MIN,
  DIVIDER_W,
  CHAT_DEFAULT,
} from './panelLayout.js'

describe('clampChatWidth', () => {
  const CONTAINER = 1600

  it('하한 CHAT_MIN 아래는 CHAT_MIN 으로', () => {
    expect(clampChatWidth(100, CONTAINER)).toBe(CHAT_MIN)
    expect(clampChatWidth(0, CONTAINER)).toBe(CHAT_MIN)
  })

  it('상한(우측 최소폭 보장)을 넘으면 잘린다', () => {
    const maxChat = CONTAINER - RIGHT_MIN - DIVIDER_W
    expect(clampChatWidth(CONTAINER, CONTAINER)).toBe(maxChat)
    expect(clampChatWidth(maxChat + 200, CONTAINER)).toBe(maxChat)
  })

  it('범위 안이면 그대로(반올림)', () => {
    expect(clampChatWidth(500, CONTAINER)).toBe(500)
    expect(clampChatWidth(500.6, CONTAINER)).toBe(501)
  })

  it('컨테이너가 아주 좁으면 CHAT_MIN 하한만 유지', () => {
    expect(clampChatWidth(400, 300)).toBe(CHAT_MIN)
  })

  it('비정상 입력은 CHAT_MIN', () => {
    expect(clampChatWidth(NaN, CONTAINER)).toBe(CHAT_MIN)
    expect(clampChatWidth(undefined, CONTAINER)).toBe(CHAT_MIN)
  })
})

describe('loadChatWidth / saveChatWidth', () => {
  let store
  beforeEach(() => {
    store = {}
    vi.stubGlobal('localStorage', {
      getItem: (k) => (k in store ? store[k] : null),
      setItem: (k, v) => {
        store[k] = String(v)
      },
    })
  })

  it('저장 후 로드하면 그 값', () => {
    saveChatWidth(540)
    expect(loadChatWidth()).toBe(540)
  })

  it('저장값 없으면 fallback(CHAT_DEFAULT)', () => {
    expect(loadChatWidth()).toBe(CHAT_DEFAULT)
    expect(loadChatWidth(600)).toBe(600)
  })

  it('비정상 저장값이면 fallback', () => {
    store['dk_chat_width'] = 'abc'
    expect(loadChatWidth()).toBe(CHAT_DEFAULT)
    store['dk_chat_width'] = '-5'
    expect(loadChatWidth()).toBe(CHAT_DEFAULT)
  })

  it('localStorage 부재/예외에도 크래시 없이 fallback', () => {
    vi.stubGlobal('localStorage', undefined)
    expect(loadChatWidth(480)).toBe(480)
    expect(() => saveChatWidth(500)).not.toThrow()
  })
})
