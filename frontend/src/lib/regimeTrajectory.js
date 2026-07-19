// 국면 이동 궤적(족적) 순수 로직 — 경기×심리 매트릭스 좌표 변환·셀 내 겹침 오프셋·트레일 스타일.
// 판정(cycle_score/sentiment_score/regime)은 백엔드 엔진이 결정한다. 여기선 **표시 좌표만** 계산
// (색·글리프 규칙은 컴포넌트가 theme.css 토큰으로 — 방향색 금지·주황=현재/강조).

// 축 점수(-2..+2) → 매트릭스 % 좌표. **RegimeGauge 마커와 동일 공식(SSOT)** — 게이지 점과 궤적이
// 좌표를 공유해 어긋나지 않는다. x: 심리(좌 공포 → 우 탐욕), y: 경기(위 양호 → 아래 악화).
// (0,0)=정중앙(50,50), (2,2)=우상(88,12), (-2,-2)=좌하(12,88). 값 범위상 항상 12..88.
export function regimeMarkerPos(cycleScore, sentimentScore) {
  const cs = cycleScore ?? 0
  const ss = sentimentScore ?? 0
  return {
    x: 12 + ((ss + 2) / 4) * 76,
    y: 12 + ((2 - cs) / 4) * 76,
  }
}

// 셀 내부 겹침 해소 — 점수가 정수라 같은 국면이 지속되면 같은 칸에 정확히 겹친다. 같은 셀의 k번째
// 방문(0-based, 총 n)을 해바라기(황금각) 분포로 소반경 오프셋한다(결정적·무작위 아님). 서브셀 정밀도
// 주장이 아니라 재방문/체류를 눈에 보이게 하는 가독 보조 — 반경은 셀 반폭(~9.5%) 내로 제한.
const OFFSET_R = 6 // % 단위 최대 반경
const GOLDEN_ANGLE = 2.399963229728653 // 라디안(황금각)
export function offsetForVisit(k, n) {
  if (!n || n <= 1) return { dx: 0, dy: 0 }
  const radius = OFFSET_R * Math.sqrt((k + 0.5) / n)
  const angle = k * GOLDEN_ANGLE
  return { dx: radius * Math.cos(angle), dy: radius * Math.sin(angle) }
}

// 트레일 점 불투명도 — 과거(저)→현재(고) 그라디언트. 색상은 컴포넌트가 토큰으로(과거 회색·현재 주황).
export function trailOpacity(index, n) {
  if (n <= 1) return 1
  return 0.35 + 0.55 * (index / (n - 1))
}

// rawPoints(백엔드 계약, 시간 오름차순) → 표시용 궤적. 각 점에 x,y(오프셋 반영)·isLast·isTransition·
// opacity 부여 + SVG pathD(폴리라인). 빈 입력은 {points:[], pathD:''}.
export function buildTrajectory(rawPoints) {
  const pts = Array.isArray(rawPoints) ? rawPoints : []
  const n = pts.length
  const cellKey = (p) => `${p.cycle_score},${p.sentiment_score}`

  // 1) 셀별 총 방문 수(오프셋 분산 계산용).
  const cellTotal = new Map()
  for (const p of pts) cellTotal.set(cellKey(p), (cellTotal.get(cellKey(p)) || 0) + 1)

  // 2) 시간순으로 셀 방문 인덱스 부여 + 오프셋 적용.
  const cellSeen = new Map()
  const points = pts.map((p, i) => {
    const key = cellKey(p)
    const k = cellSeen.get(key) || 0
    cellSeen.set(key, k + 1)
    const base = regimeMarkerPos(p.cycle_score, p.sentiment_score)
    const { dx, dy } = offsetForVisit(k, cellTotal.get(key))
    const prev = i > 0 ? pts[i - 1] : null
    return {
      x: base.x + dx,
      y: base.y + dy,
      date: p.date,
      regime: p.regime,
      cs: p.cycle_score,
      ss: p.sentiment_score,
      cashRatio: p.recommended_cash_ratio,
      isLast: i === n - 1,
      isTransition: prev != null && prev.regime !== p.regime,
      opacity: trailOpacity(i, n),
    }
  })

  const pathD = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(2)} ${p.y.toFixed(2)}`)
    .join(' ')
  return { points, pathD }
}
