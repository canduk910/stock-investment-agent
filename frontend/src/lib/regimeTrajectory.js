// 국면 이동 궤적 순수 로직 — 경기×심리 매트릭스 좌표 변환 + **표본별 개별 노드 궤적**(같은 칸 반복 오프셋).
// 판정(cycle_score/sentiment_score/regime)은 백엔드 엔진이 결정한다. 여기선 **표시 좌표만** 계산
// (색 규칙은 컴포넌트가 theme.css 토큰으로 — 방향색 금지·주황=현재/강조).

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

// rawPoints(백엔드 계약, 시간 오름차순·이미 범위별로 표본화됨) → **표본별 개별 노드 궤적**.
// 표본이 3~4개뿐이라 병합하지 않고 각 표본을 개별 점으로 둔다(분기/반기/연 개수를 그대로 보이게 —
// 사용자 결정). 같은 국면(같은 cs,ss=같은 좌표)이 반복되면 매트릭스상 같은 자리라 겹치므로 작은 **대각
// 오프셋**으로 떨어뜨려 개별 표시(표본 소수라 예전 36개월 나선처럼 복잡하지 않음).
//
// livePos({x,y}|null): 라이브 마커 좌표. **가장 최근 표본이 라이브와 같은 칸이면** 그 표본은 라이브
// 마커가 대표하므로 노드로 안 그리고(deferToLive) 경로만 라이브 좌표로 잇는다(현재 기간=라이브).
// 라이브 칸에 놓이는 과거 표본은 오프셋(중앙 슬롯=라이브 몫)으로 라이브 마커와 안 겹치게 한다.
//
// 반환: {nodes, visible(=deferToLive 아닌 노드), pathD(표시 노드 경로 + deferLast 면 라이브로 종결),
//   deferLast}. 각 노드: {x,y,baseX,baseY,cs,ss,regime,date,startDates:[date],isLast,opacity,deferToLive}.
// 빈 입력은 {nodes:[], visible:[], pathD:'', deferLast:false}.
const _OFFSET = { x: 3.0, y: -3.2 } // 같은 칸 반복 표본 대각 오프셋(매트릭스 100 기준 소폭)
const _clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v))

export function buildSampledTrajectory(rawPoints, livePos = null) {
  const pts = Array.isArray(rawPoints) ? rawPoints : []
  const n = pts.length
  const atLive = (x, y) =>
    livePos != null && Math.abs(x - livePos.x) < 0.01 && Math.abs(y - livePos.y) < 0.01

  const nodes = pts.map((p, i) => {
    const { x, y } = regimeMarkerPos(p.cycle_score, p.sentiment_score)
    return {
      x,
      y,
      baseX: x,
      baseY: y,
      cs: p.cycle_score,
      ss: p.sentiment_score,
      regime: p.regime,
      date: p.date,
      startDates: [p.date],
      isLast: i === n - 1,
      opacity: n <= 1 ? 1 : 0.45 + 0.55 * (i / (n - 1)), // 과거 흐림 → 최근 진함
      deferToLive: false,
    }
  })

  // 가장 최근 표본이 라이브와 같은 칸 → 라이브 마커가 그 기간 대표(노드 생략, 경로만 라이브로 종결).
  const deferLast = n > 0 && atLive(nodes[n - 1].baseX, nodes[n - 1].baseY)
  if (deferLast) nodes[n - 1].deferToLive = true

  // 같은 기본 좌표(같은 국면 반복) 노드를 작은 대각 오프셋으로 분리. 라이브 칸이면 중앙(슬롯0)은 라이브
  //   마커 몫이라 실노드는 1칸부터 바깥(겹침 방지). 칸별 등장 순서로 슬롯 배정(결정적·오프셋 화면 안 클램프).
  const seen = new Map()
  for (const nd of nodes) {
    if (nd.deferToLive) continue
    const key = `${nd.baseX.toFixed(2)},${nd.baseY.toFixed(2)}`
    const seenCount = seen.get(key) ?? 0
    seen.set(key, seenCount + 1)
    const slot = atLive(nd.baseX, nd.baseY) ? seenCount + 1 : seenCount // 라이브 칸은 중앙 비움
    if (slot > 0) {
      nd.x = _clamp(nd.baseX + slot * _OFFSET.x, 8, 92)
      nd.y = _clamp(nd.baseY + slot * _OFFSET.y, 8, 92)
    }
  }

  const visible = nodes.filter((nd) => !nd.deferToLive)
  const coords = visible.map((nd) => [nd.x, nd.y])
  if (deferLast && livePos) coords.push([livePos.x, livePos.y])
  const pathD = coords
    .map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(2)} ${y.toFixed(2)}`)
    .join(' ')

  return { nodes, visible, pathD, deferLast }
}

// 라벨 **년도별 그라데이션 레벨** — 시간 방향을 색 짙기로 읽게 한다(과거년도 옅게 → 최근년도 짙게).
// 라벨 그룹에 대표 년도(그룹 내 가장 최근 startDate 의 연도 — 재방문 셀이 여러 해면 최근 해로, 그룹 opacity
// 최댓값 관점과 동일)를 매기고, 그 화면에 등장한 **서로 다른 연도**를 오래→최근으로 정렬해 0..N-1 인덱스를
// 4단계 밝기 램프(0=옅은 회색 muted → 3=짙은 남색 navy, styles.css `.rtraj__stoplabel--y0..y3`)에 매핑한다.
// **판정 아님·표시만**: 색 토큰만 쓰고(방향색/경보색 금지), 같은 해 라벨은 같은 짙기가 되도록 연도 인덱스로만
// 정한다(월별로 흩지 않음 = 사용자 요구 "년도별"). 단일 연도(대비 없음)·연도 불명은 레벨 0(현 회색 유지·무해).
// 라벨 세로 위치 — 점 위/아래 바깥에 두되, **매트릭스 상/하단(축 pole 라벨 '경기 양호'·'경기 악화' 구역)과
// 겹치지 않게** 가장자리에서는 안쪽으로 뒤집는다. y<20(상단 경기 양호 근처)→점 아래(down)·y>80(하단
// 경기 악화 근처)→점 위(up)·그 외는 위/아래 절반 규칙. up/down 은 라벨 종류별 여백(px, viewBox 0..100).
export function placeLabelY(y, up, down) {
  if (y < 20) return y + down // 상단 → 아래로(경기 양호 pole 회피)
  if (y > 80) return y - up // 하단 → 위로(경기 악화 pole 회피)
  return y < 50 ? y - up : y + down
}

export const LABEL_SHADE_LEVELS = 4 // styles.css 의 --y0..--y3 과 SSOT (레벨 수 바뀌면 CSS 도 함께)

export function labelYearShades(groups) {
  const arr = Array.isArray(groups) ? groups : []
  const yearOf = (g) => {
    const dates = (g?.startDates ?? []).filter((d) => typeof d === 'string' && d.length >= 4)
    if (dates.length === 0) return null
    const latest = dates.reduce((a, b) => (b > a ? b : a)) // ISO 날짜 사전식 최대 = 가장 최근
    return latest.slice(0, 4)
  }
  const withYear = arr.map((g) => ({ ...g, year: yearOf(g) }))
  const years = [...new Set(withYear.map((g) => g.year).filter(Boolean))].sort()
  const k = years.length
  const idx = new Map(years.map((y, i) => [y, i]))
  const maxLevel = LABEL_SHADE_LEVELS - 1
  return withYear.map((g) => ({
    ...g,
    // k<=1(대비 없음) 또는 연도 불명 → 레벨 0(현 회색 유지). 그 외 오래(0)→최근(maxLevel) 균등 매핑.
    shadeLevel: g.year == null || k <= 1 ? 0 : Math.round((idx.get(g.year) / (k - 1)) * maxLevel),
  }))
}
