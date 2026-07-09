import { useEffect } from 'react'

// 팝업 모달 셸 — 오버레이 + 닫기. 브라우저 modal dialog(alert/confirm/prompt) 금지 규칙 준수:
// 여기서 쓰는 role="dialog"/aria-modal 은 ARIA 시맨틱일 뿐 브라우저 대화상자를 띄우지 않는다.
// 닫기: ✕ 버튼 · 오버레이 클릭 · Escape. 열려 있는 동안 배경 스크롤을 잠근다.
export default function Modal({ title, onClose, children }) {
  useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [onClose])

  return (
    <div className="modal__overlay" role="presentation" onMouseDown={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(e) => e.stopPropagation()} // 내용 클릭은 닫기로 전파되지 않게
      >
        <header className="modal__head">
          <h2 className="modal__title">{title}</h2>
          <button type="button" className="modal__close" onClick={onClose} aria-label="닫기">
            ✕
          </button>
        </header>
        <div className="modal__body">{children}</div>
      </div>
    </div>
  )
}
