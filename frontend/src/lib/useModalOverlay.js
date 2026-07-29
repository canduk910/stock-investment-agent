import { useEffect, useRef } from 'react'

// 오버레이 접근성 로직 SSOT — 딤 배경 상세 오버레이(시황 상세·지표 히스토리)가 공유하던
// 동일 useEffect(닫기버튼 포커스 + Esc 닫힘 + 배경 스크롤 잠금/복원)를 훅 하나로 통합.
// 마크업·스타일은 각 오버레이가 소유한다(범용 Modal.jsx 부활 아님 — 로직만 공유).
//
// 사용: `const closeRef = useModalOverlay(onClose)` → 닫기(✕) 버튼에 `ref={closeRef}`.
// 동작(기존 두 구현과 바이트 동일):
//   1) 마운트 시 닫기 버튼에 포커스(키보드 사용자가 바로 닫을 수 있게 — 접근성).
//   2) document keydown 에서 Escape → onClose() (브라우저 dialog 금지 관습 하의 닫기 경로).
//   3) body overflow 를 'hidden' 으로 잠그고, 언마운트 시 이전 값 복원(배경 스크롤 방지).
export function useModalOverlay(onClose) {
  const closeRef = useRef(null)

  useEffect(() => {
    closeRef.current?.focus() // 열릴 때 닫기 버튼 포커스(접근성)
    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden' // 배경 스크롤 잠금
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow // 이전 값 복원(다른 화면 영향 0)
    }
  }, [onClose])

  return closeRef
}
