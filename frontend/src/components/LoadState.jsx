// 로딩/에러/재시도 상태 박스 SSOT — `popup__state` 3분기(로딩 중… / 실패+재시도 / 본문)를
// 컴포넌트마다 손으로 반복하던 보일러플레이트의 단일 출처(M6).
//
// 설계 원칙(행동 보존·편차 흡수):
//   - 박스 클래스는 popup__state 고정(이 클래스를 쓰는 자리만 통합 대상 — wl__state·rtraj__state 등
//     자리 전용 상태 클래스는 각자 유지, 억지 통합하지 않는다).
//   - 문구·에러 본문은 각 자리가 소유: loadingText(로딩 문구)·errorContent(에러 노드 —
//     span 래핑 여부까지 호출부가 결정해 기존 DOM 그대로).
//   - 재시도 버튼은 onRetry 가 있을 때만(지표 히스토리 오버레이처럼 재시도 없는 자리 지원).
//     라벨·클래스도 prop(기본 '↻ 재시도'/'refresh' — AdminPanel 은 '다시 시도'/'refresh admin__retry').
//   - 무한 스피너 금지 관습의 짝: 에러 분기가 항상 명시적 안내(+재시도)로 귀결되게 구조로 유도.
//
// 사용형 2가지(호출부 제어 흐름 보존):
//   ① 조기 반환형: if (loading) return <LoadState loading loadingText="…"/> …
//   ② 래퍼형: <LoadState loading={l} … error={e} …>{본문}</LoadState> (둘 다 아니면 children 반환)
export default function LoadState({
  loading = false,
  loadingText,
  error = false,
  errorContent,
  onRetry,
  retryLabel = '↻ 재시도',
  retryClassName = 'refresh',
  children = null,
}) {
  if (loading) return <div className="popup__state">{loadingText}</div>
  if (error) {
    return (
      <div className="popup__state">
        {errorContent}
        {onRetry ? (
          <button type="button" className={retryClassName} onClick={onRetry}>
            {retryLabel}
          </button>
        ) : null}
      </div>
    )
  }
  return children
}
