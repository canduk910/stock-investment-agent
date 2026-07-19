// 국면 이동 궤적 순수 로직 — 경기×심리 매트릭스 좌표 변환 + **단순 경로**(인접 동일 셀 접기).
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

// rawPoints(백엔드 계약, 시간 오름차순) → **단순 경로**. 인접한 동일 셀(같은 cs,ss) 월들을 하나의
// '정차점'으로 접어(dwell=머문 개월수) 점 수를 크게 줄인다 — 복잡한 셀 내 오프셋·다중 화살표를 없애고
// 정차점 중심을 잇는 깔끔한 폴리라인 하나만 만든다(방향은 끝점 화살표 하나로). 각 정차점에 x,y·regime·
// dwell·startDate/endDate·isFirst/isLast·opacity(과거 흐림→현재 진함) 부여 + SVG pathD.
// 빈 입력은 {stops:[], pathD:''}.
export function buildRegimePath(rawPoints) {
  const pts = Array.isArray(rawPoints) ? rawPoints : []
  const stops = []
  for (const p of pts) {
    const prev = stops[stops.length - 1]
    if (prev && prev.cs === p.cycle_score && prev.ss === p.sentiment_score) {
      prev.endDate = p.date // 같은 셀 지속 → 정차 연장
      prev.dwell += 1
    } else {
      const { x, y } = regimeMarkerPos(p.cycle_score, p.sentiment_score)
      stops.push({
        x,
        y,
        cs: p.cycle_score,
        ss: p.sentiment_score,
        regime: p.regime,
        startDate: p.date,
        endDate: p.date,
        dwell: 1,
      })
    }
  }

  const n = stops.length
  stops.forEach((s, i) => {
    s.isFirst = i === 0
    s.isLast = i === n - 1
    s.opacity = n <= 1 ? 1 : 0.45 + 0.55 * (i / (n - 1)) // 과거→현재 진하게
  })

  const pathD = stops
    .map((s, i) => `${i === 0 ? 'M' : 'L'}${s.x.toFixed(2)} ${s.y.toFixed(2)}`)
    .join(' ')
  return { stops, pathD }
}

// 재방문 셀(같은 좌표)의 정차점 라벨이 겹치는 문제 — 좌표별로 시작월(startDate)들을 **한 자리에 모은다**.
// 반환: [{x, y, opacity(그 좌표 중 최댓값=가장 최근), startDates:[시간순]}]. 컴포넌트가 ym 포맷 + ", " 조인해
// 한 라벨로 표시(예: "24.01, 24.05"). 좌표는 float 이라 소수 2자리로 키잉(regimeMarkerPos 값은 안정적).
export function stopLabelGroups(stops) {
  const arr = Array.isArray(stops) ? stops : []
  const byCoord = new Map()
  for (const s of arr) {
    const key = `${s.x.toFixed(2)},${s.y.toFixed(2)}`
    const g = byCoord.get(key)
    if (g) {
      g.startDates.push(s.startDate)
      if (s.opacity > g.opacity) g.opacity = s.opacity
    } else {
      byCoord.set(key, { x: s.x, y: s.y, opacity: s.opacity, startDates: [s.startDate] })
    }
  }
  return [...byCoord.values()]
}

// 라벨 **년도별 그라데이션 레벨** — 시간 방향을 색 짙기로 읽게 한다(과거년도 옅게 → 최근년도 짙게).
// 라벨 그룹에 대표 년도(그룹 내 가장 최근 startDate 의 연도 — 재방문 셀이 여러 해면 최근 해로, 그룹 opacity
// 최댓값 관점과 동일)를 매기고, 그 화면에 등장한 **서로 다른 연도**를 오래→최근으로 정렬해 0..N-1 인덱스를
// 4단계 밝기 램프(0=옅은 회색 muted → 3=짙은 남색 navy, styles.css `.rtraj__stoplabel--y0..y3`)에 매핑한다.
// **판정 아님·표시만**: 색 토큰만 쓰고(방향색/경보색 금지), 같은 해 라벨은 같은 짙기가 되도록 연도 인덱스로만
// 정한다(월별로 흩지 않음 = 사용자 요구 "년도별"). 단일 연도(대비 없음)·연도 불명은 레벨 0(현 회색 유지·무해).
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
