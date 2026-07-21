import { useEffect, useRef, useState } from 'react'
import {
  fetchMarketOutlook,
  fetchNaverMarketOutlook,
  streamFetchMarketOutlook,
  fetchMarketOutlookSummary,
} from '../api.js'
import { isOutlookStale, todayStampKST } from '../lib/marketOutlook.js'
import { applyProgressEvent } from './FetchProgress.jsx'
import RegimeGauge from './RegimeGauge.jsx'
import DailySummary from './DailySummary.jsx'
import MarketOutlookSection from './MarketOutlookSection.jsx'

// 자동 최신화 중복 방지 가드 — 날짜별 1회(패널 반복 오픈 폭주 방지).
const AUTO_FETCH_KEY = 'mo_autofetch_date'
// 금일의 요약 하루 1회 캐시(재오픈 시 재생성 없이 재사용) — {date, res}.
const DAILY_SUMMARY_KEY = 'mo_daily_summary'

function readCachedSummary(today) {
  try {
    const raw = localStorage.getItem(DAILY_SUMMARY_KEY)
    if (!raw) return null
    const obj = JSON.parse(raw)
    return obj && obj.date === today ? obj.res : null
  } catch {
    return null
  }
}
function writeCachedSummary(today, res) {
  try {
    localStorage.setItem(DAILY_SUMMARY_KEY, JSON.stringify({ date: today, res }))
  } catch {
    /* localStorage 불가 환경 — 캐시 없이 진행 */
  }
}

// 시장국면 대시보드 컨테이너 — 시황 lifecycle(수집·요약) **단일 소유**. 레이아웃(사용자 요청):
//   [금일의 요약(최상단·자동)] → [시장국면 판정(RegimeGauge)] → [증권사 시황 리포트 카드].
// 패널 로드 시 **[네이버 최신 시황 가져오기 → 요약 생성]이 차례로 자동 실행**(하루 1회 가드·재오픈 재사용).
// 시황 요약은 리포트 인용(면책)이고 시장 판정은 코드(RegimeGauge=매크로 엔진)다.
export default function MacroDashboard({ sessionId, onConsult } = {}) {
  const [reports, setReports] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [fetching, setFetching] = useState(false)
  const [fetchMsg, setFetchMsg] = useState(null)
  const [progress, setProgress] = useState(null) // SSE 진행 체크리스트
  const [autoNote, setAutoNote] = useState(null) // 자동 최신화 안내(수동과 구분)
  const autoTriedRef = useRef(false) // 마운트당 자동 오케스트레이션 1회(StrictMode 방어)

  // 금일의 요약(종합) 상태 — 컨테이너가 소유(자동 생성 오케스트레이션).
  const [summaryState, setSummaryState] = useState('idle') // idle | loading | done | error
  const [summaryData, setSummaryData] = useState(null)
  const [summaryErr, setSummaryErr] = useState(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchMarketOutlook()
      const list = data.reports ?? []
      setReports(list)
      return list
    } catch (e) {
      setError(e.message)
      setReports(null)
      return null // 에러는 null(빈 배열 []=조회성공·저장0 과 구분 — 자동 최신화 게이트에서 사용)
    } finally {
      setLoading(false)
    }
  }

  // 금일의 요약 생성(LLM 종합 1회) → 성공 시 하루 캐시 저장. 수동 '다시 생성'·수집 직후 강제 생성 공용.
  async function generateSummary() {
    setSummaryState('loading')
    setSummaryErr(null)
    try {
      const res = await fetchMarketOutlookSummary()
      if (res.validation_failed || !res.summary) {
        setSummaryState('error')
        setSummaryErr(res.message || '금일의 요약을 생성하지 못했습니다.')
      } else {
        setSummaryData(res)
        setSummaryState('done')
        writeCachedSummary(todayStampKST(), res) // 하루 1회 재사용 캐시
      }
    } catch (e) {
      setSummaryState('error')
      setSummaryErr(`금일의 요약 생성 실패(${e.message}).`)
    }
  }

  // 저장 시황이 있으면 금일의 요약 준비. force=수집 직후(항상 최신 반영·재생성), 아니면 하루 캐시 재사용,
  //   캐시 없으면 1회 생성. LLM 비용은 하루 1회로 제한(사용자 결정).
  function maybeAutoSummary(list, { force = false } = {}) {
    if (!list || list.length === 0) return
    if (force) {
      generateSummary()
      return
    }
    const cached = readCachedSummary(todayStampKST())
    if (cached) {
      setSummaryData(cached)
      setSummaryState('done') // 오늘 이미 생성 → 재사용(LLM 미호출)
    } else {
      generateSummary()
    }
  }

  // 네이버 최신 시황 SSE 수집 → 완료 후 재조회 → [순차] 금일의 요약 재생성(수집 직후 항상 갱신).
  async function fetchNaver() {
    setFetching(true)
    setFetchMsg(null)
    setProgress({ stage: 'list', reports: [], done: 0, total: 0 })
    let finished = false
    await streamFetchMarketOutlook({
      limit: 15,
      onEvent: (ev) => {
        if (ev.type === 'done') {
          finished = true
          setFetchMsg(`새 요약 ${ev.new}건 · 확인 ${ev.fetched}건` + (ev.failed ? ` · 실패 ${ev.failed}건` : ''))
        } else if (ev.type === 'error') {
          finished = true
          setFetchMsg(`수집 실패(${ev.message}).`)
        } else {
          setProgress((p) => applyProgressEvent(p, ev))
        }
      },
      onError: async () => {
        if (finished) return
        try {
          const res = await fetchNaverMarketOutlook(15)
          setFetchMsg(`새 요약 ${res.new}건 · 확인 ${res.fetched}건` + (res.failed ? ` · 실패 ${res.failed}건` : ''))
        } catch (e) {
          setFetchMsg(`수집 실패(${e.message}).`)
        }
      },
    })
    setProgress(null)
    const fresh = await load()
    setFetching(false)
    setAutoNote(null)
    maybeAutoSummary(fresh, { force: true }) // [수집 → 요약] 순차 — 수집 직후 항상 요약 갱신
  }

  // 저장 최신 시황이 오늘(KST) 아니면 자동 수집(하루 1회 가드) → 수집 후 요약. 이미 최신이면 곧바로 요약.
  function maybeAutoRefresh(list) {
    if (!isOutlookStale(list, todayStampKST())) {
      maybeAutoSummary(list) // 이미 최신 → 하루 캐시 재사용/1회 생성
      return
    }
    const today = todayStampKST()
    let alreadyFetched = false
    try {
      alreadyFetched = localStorage.getItem(AUTO_FETCH_KEY) === today
      if (!alreadyFetched) localStorage.setItem(AUTO_FETCH_KEY, today)
    } catch {
      /* localStorage 불가 — 그래도 마운트당 1회는 진행(autoTriedRef) */
    }
    if (alreadyFetched) {
      maybeAutoSummary(list) // 오늘 이미 수집 시도함 → 요약만(캐시 재사용/1회)
      return
    }
    setAutoNote('오늘 최신 시황을 자동으로 확인하는 중…')
    fetchNaver() // 수집 → (완료 후) 요약
  }

  useEffect(() => {
    ;(async () => {
      const list = await load()
      if (autoTriedRef.current) return
      autoTriedRef.current = true
      // load 실패(null) 시 자동 최신화 스킵 — 백엔드 장애에서 진행바+에러 동시표시·헛수집 방지.
      //   (빈 배열 []=조회 성공·저장 0 은 자동 수집 대상 = 신규 유저.)
      if (list !== null) maybeAutoRefresh(list)
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <>
      {/* 금일의 요약 — 최상단(저장 시황 있거나 생성이 진행/완료됐을 때). */}
      {(reports && reports.length > 0) || summaryState !== 'idle' ? (
        <DailySummary
          state={summaryState}
          data={summaryData}
          errMsg={summaryErr}
          onGenerate={generateSummary}
        />
      ) : null}

      {/* 시장국면 판정(코드/매크로 엔진) */}
      <RegimeGauge />

      {/* 증권사 시황 리포트 카드(controlled — 컨테이너가 lifecycle 소유) */}
      <MarketOutlookSection
        reports={reports}
        loading={loading}
        error={error}
        fetching={fetching}
        progress={progress}
        fetchMsg={fetchMsg}
        autoNote={autoNote}
        onFetch={fetchNaver}
        onReload={load}
        sessionId={sessionId}
        onConsult={onConsult}
      />
    </>
  )
}
