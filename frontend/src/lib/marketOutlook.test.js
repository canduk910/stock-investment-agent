import { describe, it, expect } from 'vitest'
import {
  groupReportsByDate,
  threeLineSummary,
  isOutlookStale,
  todayStampKST,
} from './marketOutlook.js'

// 시황 표현 로직(순수) — 일별 그룹핑 + 3줄요약 추출. 브라우저 없이 테스트.
// 계약: 백엔드 응답 reports[] 는 date 내림차순(최신순). date="YY.MM.DD"|"YYYY.MM.DD" 문자열.

describe('groupReportsByDate — 작성일별 구분(항목4)', () => {
  it('같은 날짜끼리 묶고, 입력(최신순) 순서를 보존한다', () => {
    const reports = [
      { report_id: 'a', date: '26.07.10' },
      { report_id: 'b', date: '26.07.10' },
      { report_id: 'c', date: '26.07.08' },
    ]
    const groups = groupReportsByDate(reports)
    expect(groups.map((g) => g.date)).toEqual(['26.07.10', '26.07.08'])
    expect(groups[0].reports.map((r) => r.report_id)).toEqual(['a', 'b'])
    expect(groups[1].reports.map((r) => r.report_id)).toEqual(['c'])
  })

  it('날짜 결측(없음/빈문자열)은 하나의 버킷으로 묶어 맨 끝에 둔다', () => {
    const reports = [
      { report_id: 'a', date: '26.07.10' },
      { report_id: 'b' }, // date 없음
      { report_id: 'c', date: '' }, // 빈 문자열
    ]
    const groups = groupReportsByDate(reports)
    expect(groups[0].date).toBe('26.07.10')
    const last = groups[groups.length - 1]
    expect(last.date).toBeNull()
    expect(last.reports.map((r) => r.report_id)).toEqual(['b', 'c'])
  })

  it('비배열 입력 → 빈 배열(방어)', () => {
    expect(groupReportsByDate(null)).toEqual([])
    expect(groupReportsByDate(undefined)).toEqual([])
  })
})

describe('threeLineSummary — 3줄요약 추출(세줄요약 우선, 핵심요지 폴백)', () => {
  it('세줄요약이 있으면 그대로 반환', () => {
    const s = { 세줄요약: ['라인1', '라인2', '라인3'], 핵심요지: ['x', 'y', 'z', 'w'] }
    expect(threeLineSummary(s)).toEqual(['라인1', '라인2', '라인3'])
  })

  it('세줄요약이 없으면(구 레코드) 핵심요지 최대 3개로 폴백', () => {
    const s = { 핵심요지: ['a', 'b', 'c', 'd'] }
    expect(threeLineSummary(s)).toEqual(['a', 'b', 'c'])
  })

  it('세줄요약이 빈 배열이면 핵심요지로 폴백', () => {
    const s = { 세줄요약: [], 핵심요지: ['a'] }
    expect(threeLineSummary(s)).toEqual(['a'])
  })

  it('둘 다 없거나 summary 결측 → 빈 배열', () => {
    expect(threeLineSummary({})).toEqual([])
    expect(threeLineSummary(null)).toEqual([])
    expect(threeLineSummary(undefined)).toEqual([])
  })
})

describe('isOutlookStale — 저장 최신 시황이 오늘이 아니면 stale(자동 최신화 트리거)', () => {
  it('빈 배열/비배열 → stale(수집 필요)', () => {
    expect(isOutlookStale([], '26.07.13')).toBe(true)
    expect(isOutlookStale(null, '26.07.13')).toBe(true)
  })

  it('최신(첫 항목) 날짜 == 오늘 → fresh(수집 불필요)', () => {
    const reports = [{ date: '26.07.13' }, { date: '26.07.10' }]
    expect(isOutlookStale(reports, '26.07.13')).toBe(false)
  })

  it('최신 날짜 != 오늘 → stale', () => {
    const reports = [{ date: '26.07.10' }, { date: '26.07.08' }]
    expect(isOutlookStale(reports, '26.07.13')).toBe(true)
  })

  it('최신 항목 날짜 결측 → stale(안전 폴백)', () => {
    expect(isOutlookStale([{ date: '' }], '26.07.13')).toBe(true)
    expect(isOutlookStale([{}], '26.07.13')).toBe(true)
  })
})

describe('todayStampKST — KST 오늘 "YY.MM.DD"(네이버 날짜 형식)', () => {
  it('YY.MM.DD 2자리 형식', () => {
    expect(todayStampKST()).toMatch(/^\d{2}\.\d{2}\.\d{2}$/)
  })
})
