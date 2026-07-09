import { useEffect, useState } from 'react'
import { fetchStockBundle } from '../api.js'
import StockReportView from './StockReportView.jsx'

// 챗 팝업(show_stock_report) 본문 — 기존 StockReportView(3단 리포트)를 재사용한다.
// 팝업 실데이터는 LLM 응답이 아니라 프론트가 ticker 로 fetchStockBundle 을 직접 1회 조회한다
// (환각 차단 + 최신성, 현재가 무캐시 — 팝업 열 때마다 조회). 섹션 실패(partial_failure)는
// 200 정상 응답이라 그대로 렌더(StockReportView 가 섹션별 "일시 조회 불가" 처리).
// 네트워크/HTTP 오류만 여기서 잡아 재시도 버튼으로 안내한다(무한 스피너·샘플 위장 금지).
export default function PopupStockReport({ ticker, stockName }) {
  const [bundle, setBundle] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      setBundle(await fetchStockBundle(ticker))
    } catch (e) {
      setError(e.message)
      setBundle(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker])

  if (loading) {
    return (
      <div className="popup__state">
        {stockName ? `${stockName}(${ticker})` : ticker} 리포트 조회 중…
      </div>
    )
  }
  if (error || !bundle) {
    return (
      <div className="popup__state">
        <span>리포트 조회 실패: {error ?? '데이터 없음'}</span>
        <button type="button" className="refresh" onClick={load}>
          ↻ 재시도
        </button>
      </div>
    )
  }
  return <StockReportView bundle={bundle} />
}
