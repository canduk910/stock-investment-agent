import { useCallback, useEffect, useState } from 'react'

// 조회 상태 훅 — {data, loading, error, reload}. 컴포넌트가 반복하던
// useState(null/true/null) + load() + useEffect 패턴의 단일 출처(신규 패널 추가 시 재사용).
//
// - loading 초기 true, reload 시작 시 error clear(재조회 낙관).
// - 성공: data=결과 + onData(있으면 부모 통지). 실패: error=e.message(data 는 유지 — 에러 분기가
//   먼저 렌더되므로 stale/null 무관). partial_failure 는 200 정상 응답이라 여기서 throw 되지 않는다.
// - apiCall: () => Promise<data>. deps: 변화 시 재조회(기본 []=마운트 1회). onData: 성공 콜백(옵션).
export function useFetch(apiCall, deps = [], onData) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const reload = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await apiCall()
      setData(res)
      if (onData) onData(res)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
    // deps 는 호출부가 지정(정렬 등 재조회 무관 값은 제외). apiCall/onData 항등성은 호출부 책임.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    reload()
  }, [reload])

  return { data, loading, error, reload }
}
