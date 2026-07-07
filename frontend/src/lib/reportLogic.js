// 종목 리포트 표현 분기 — 순수 판정 로직(계약 경계). 브라우저 없이 테스트 가능.
// 숫자·밸류에이션 판정은 백엔드(stock/summary.py)가 확정한다. 여기서는 "어떻게 보여줄지"만 결정한다.
// TDD: reportLogic.test.js 가 partial_failure·게이트·YoY 방향의 계약을 고정한다.

// partial_failure 에 해당 섹션이 있으면 true → "일시 조회 불가" 안내로 표시.
// 백엔드가 문자열 리스트(['financials'])로 주지만, 객체({section,reason}) 형태도 방어적으로 수용.
export function sectionFailed(partialFailure, section) {
  if (!Array.isArray(partialFailure)) return false
  return partialFailure.some((entry) => {
    if (typeof entry === 'string') return entry === section
    return entry?.section === section
  })
}

// avg_per/valuation_label 게이트 — 둘 다 있어야 밸류에이션 판정을 노출한다.
// 하나라도 null 이면 "밸류에이션 판정 준비 중"(데이터 검증 게이트, 임의 라벨 금지).
export function isValuationReady(summary) {
  if (!summary) return false
  return summary.avg_per !== null && summary.avg_per !== undefined &&
    summary.valuation_label !== null && summary.valuation_label !== undefined
}

function isFiniteNum(v) {
  return typeof v === 'number' && Number.isFinite(v)
}

// 전기 대비 증감 — 재무추이 테이블 YoY. 방향은 dir 문자열('up'/'down'/'flat'/null)로 주어
// 색만으로 구분하지 않게 한다(디자인 시스템 §4 — ▲▼ 글리프 병기). 색: up=파랑/down=회색.
// 전기값이 0 이하이거나 없으면 pct=null(0 나눗셈·부호역전 방지). 현재값 결측이면 전부 null.
export function yoyChange(curr, prev) {
  if (!isFiniteNum(curr)) return { delta: null, pct: null, dir: null }
  if (!isFiniteNum(prev)) return { delta: null, pct: null, dir: null }
  const delta = curr - prev
  const dir = delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat'
  const pct = prev > 0 ? (delta / prev) * 100 : null
  return { delta, pct, dir }
}
