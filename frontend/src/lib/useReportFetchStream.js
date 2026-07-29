import { useState } from 'react'
import { applyProgressEvent } from '../components/FetchProgress.jsx'

// SSE 리포트 수집 결과 안내문 SSOT — done 이벤트/논스트림 응답의 {new,fetched,failed} 공용.
// 네 군데(시황·애널리스트 각 onEvent/onError)에서 손으로 재조립하던 문자열의 단일 출처.
export function formatFetchResult(res) {
  return (
    `새 요약 ${res.new}건 · 확인 ${res.fetched}건` + (res.failed ? ` · 실패 ${res.failed}건` : '')
  )
}

// 리포트 수집 SSE 오케스트레이션 훅 SSOT — 시황(MacroDashboard)·애널리스트(AnalystReportsSection)가
// 각자 ~30줄씩 복제하던 [진행 초기화 → 스트림 소비 → done/error 안내 → 끊김 시 논스트림 폴백 →
// 진행 종료 → 재조회 → fetching 해제] 상태기계를 통합한다.
//
// 사용:
//   const { fetching, fetchMsg, progress, run } = useReportFetchStream()
//   await run(
//     (handlers) => streamFetchStockReports(ticker, { limit: 10, ...handlers }), // SSE 스트림
//     () => fetchNaverStockReports(ticker, 10),                                  // 끊김 폴백(논스트림)
//     load,                                                                      // 완료 후 재조회
//   )
//
// 동작(두 원본과 동일 순서 — 계약):
//   1) fetching=true·안내문 초기화·progress={stage:'list',...}(진행 체크리스트 시작)
//   2) 스트림 이벤트: done→완료 안내(formatFetchResult)·error→실패 안내·그 외→applyProgressEvent 리듀서
//   3) onError(스트림 끊김): done/error 를 이미 받았으면 무시(finished 가드), 아니면 논스트림
//      폴백 1회(성공=완료 안내/실패=실패 안내) — 무한 스피너 금지 관습
//   4) progress=null(진행바 제거) → after()(재조회 등) → fetching=false. after 반환값을 그대로
//      돌려줘 호출부 후속 로직(예: 시황 수집 직후 금일의 요약 재생성)이 최신 목록을 쓸 수 있게 한다.
export function useReportFetchStream() {
  const [fetching, setFetching] = useState(false)
  const [fetchMsg, setFetchMsg] = useState(null)
  const [progress, setProgress] = useState(null)

  async function run(streamFn, fallbackFn, after) {
    setFetching(true)
    setFetchMsg(null)
    setProgress({ stage: 'list', reports: [], done: 0, total: 0 })
    let finished = false // done/error 프레임 수신 여부 — 수신 후의 onError(연결 종료 등)는 무시
    await streamFn({
      onEvent: (ev) => {
        if (ev.type === 'done') {
          finished = true
          setFetchMsg(formatFetchResult(ev))
        } else if (ev.type === 'error') {
          finished = true
          setFetchMsg(`수집 실패(${ev.message}).`)
        } else {
          // stage/found/progress 프레임 → 진행 체크리스트 리듀서(FetchProgress SSOT)
          setProgress((p) => applyProgressEvent(p, ev))
        }
      },
      onError: async () => {
        if (finished) return
        // 스트림 미완료(끊김) → non-stream fetch 폴백(무한 스피너 방지).
        try {
          setFetchMsg(formatFetchResult(await fallbackFn()))
        } catch (e) {
          setFetchMsg(`수집 실패(${e.message}).`)
        }
      },
    })
    setProgress(null)
    const result = after ? await after() : undefined
    setFetching(false)
    return result
  }

  return { fetching, fetchMsg, progress, run, setFetchMsg }
}
