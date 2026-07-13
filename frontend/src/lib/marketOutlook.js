// 시황(market outlook) 표현 로직(순수) — 브라우저 없이 테스트 가능(marketOutlook.test.js).
// 원칙: 백엔드가 date 내림차순으로 준 reports[] 를 프론트가 "어떻게 묶고 요약해 표시할지"만 결정.
//   재조회·판정 없음(시황 요약은 리포트 인용, 판정은 코드/매크로 엔진).

// reports[] → [{date, reports:[...]}]. 같은 date 끼리 묶고 입력(최신순) 순서 보존.
// date 결측(없음/빈문자열)은 하나의 버킷(date=null)으로 묶어 맨 끝에 둔다.
export function groupReportsByDate(reports) {
  if (!Array.isArray(reports)) return []
  const groups = []
  const byDate = new Map() // date → group 참조(첫 등장 순서 유지)
  let undated = null
  for (const r of reports) {
    const date = r && typeof r.date === 'string' && r.date.trim() ? r.date : null
    if (date === null) {
      if (!undated) undated = { date: null, reports: [] }
      undated.reports.push(r)
      continue
    }
    let group = byDate.get(date)
    if (!group) {
      group = { date, reports: [] }
      byDate.set(date, group)
      groups.push(group)
    }
    group.reports.push(r)
  }
  if (undated) groups.push(undated) // 날짜 미상은 항상 맨 끝
  return groups
}

// summary → 3줄요약 문자열 배열. 세줄요약(신규 스키마) 우선, 없으면 핵심요지 최대 3개 폴백(구 레코드).
// 둘 다 없으면 []. 카드 미리보기용.
export function threeLineSummary(summary) {
  if (!summary || typeof summary !== 'object') return []
  const three = summary.세줄요약
  if (Array.isArray(three) && three.length > 0) return three
  const key = summary.핵심요지
  if (Array.isArray(key) && key.length > 0) return key.slice(0, 3)
  return []
}
