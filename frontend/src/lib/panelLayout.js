/**
 * 좌(채팅)·우(콘텐츠) 2컬럼 분할 크기 조절 — 순수 계산 + 영속(localStorage).
 *
 * 사용자 결정: **화면 전체폭 사용**(앱 max-width 캡 제거) + **분할선 드래그로 좌/우 비율 자유 배분**.
 * 여기서는 폭 계산·클램프·영속만(순수) — DOM/드래그 배선은 App.jsx.
 */
export const CHAT_MIN = 320 // 채팅 최소폭(px)
export const RIGHT_MIN = 420 // 우측 콘텐츠 최소폭(px) — 어떤 드래그에서도 이만큼은 보장
export const DIVIDER_W = 14 // 분할선 컬럼 폭(px)
export const CHAT_DEFAULT = 420 // 기본 채팅폭(더블클릭 리셋 값)
const STORAGE_KEY = 'dk_chat_width'

/**
 * 채팅폭(px)을 [CHAT_MIN, containerWidth - RIGHT_MIN - DIVIDER_W] 로 클램프.
 * 우측 콘텐츠 최소폭을 항상 보장하고, 컨테이너가 좁으면 CHAT_MIN 하한만 지킨다.
 */
export function clampChatWidth(px, containerWidth) {
  const maxChat = Math.max(CHAT_MIN, (Number(containerWidth) || 0) - RIGHT_MIN - DIVIDER_W)
  const n = Number(px)
  if (!Number.isFinite(n)) return CHAT_MIN
  return Math.round(Math.min(Math.max(n, CHAT_MIN), maxChat))
}

/** 저장된 채팅폭(px) 로드. 없거나 비정상이면 fallback. */
export function loadChatWidth(fallback = CHAT_DEFAULT) {
  try {
    const raw = globalThis.localStorage?.getItem(STORAGE_KEY)
    const n = raw == null ? NaN : Number(raw)
    return Number.isFinite(n) && n > 0 ? n : fallback
  } catch {
    return fallback
  }
}

/** 채팅폭(px) 저장. localStorage 불가 환경(사파리 프라이빗 등)은 조용히 무시. */
export function saveChatWidth(px) {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, String(Math.round(Number(px))))
  } catch {
    /* 세션 내 상태(state)는 유지되므로 영속 실패는 치명적이지 않다 */
  }
}
