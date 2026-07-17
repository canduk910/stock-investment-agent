// 고지로(小次郎講師) 이동평균선 대순환 표현 로직(순수) — 브라우저 없이 테스트 가능(grandCycle.test.js).
// 원칙: 단계·밴드·전환 판정은 백엔드 엔진(stock/summary.py::_ma_grand_cycle)이 확정하고, 여기서는
//   그 구조화 결과를 "어떻게 표시할지"만(6-스텝 라벨·방향 글리프·밴드 문자열·서술). 재판정 없음.
//   서술은 방법론 인용일 뿐 매매 지시가 아니다(면책은 컴포넌트가 고정 표시).

// indicator_config.grand_cycle(catalog) + 현재 단계(current) → 6-스텝 리스트(현재만 isCurrent).
// catalog/stages 결측이면 빈 배열(graceful — 6단계 라벨을 프론트가 복제하지 않으므로).
export function grandCycleStages(catalog, current) {
  const stages = catalog && Array.isArray(catalog.stages) ? catalog.stages : []
  return stages.map((s) => ({
    stage: s.stage,
    name: s.name,
    arrangement: s.arrangement,
    phase: s.phase,
    isCurrent: current != null && s.stage === current,
  }))
}

// 국면 → 방향 글리프. 색이 아니라 형태로 방향을 표기(가격 방향색 오용 금지 규칙 준수).
export function stageGlyph(phase) {
  if (phase === '상승') return '▲'
  if (phase === '하락') return '▼'
  if (phase === '전환') return '◆'
  return '─'
}

// 밴드폭(부호 포함) + 방향(확대/축소/유지). 결측이면 —.
export function bandReadout(gc) {
  const v = gc ? gc.band_width_pct : null
  if (v == null || !Number.isFinite(Number(v))) return '—'
  const n = Number(v)
  const base = `${n > 0 ? '+' : ''}${n.toFixed(2)}%`
  return gc.band_direction ? `${base} · ${gc.band_direction}` : base
}

// 대순환 구조화 결과 → 방법론 인용 서술 문장(단계·밴드·지속·전환·국면). 매매 지시·수익 보장 표현 없음.
// gc 없음 → '' , 단계 미판정(동률) → 보류 안내.
export function grandCycleInsight(gc) {
  if (!gc) return ''
  if (gc.stage == null) {
    return '현재 이동평균선 배열이 동률에 가까워 대순환 단계 판정을 보류합니다.'
  }
  const parts = []
  parts.push(
    `고지로 이동평균선 대순환 방법론상 현재 ${gc.stage}단계 '${gc.stage_name}'(${gc.arrangement})입니다.`,
  )
  parts.push(`단기·장기선 간격(밴드)은 ${bandReadout(gc)}이며, 이 단계가 ${gc.bars_in_stage}봉째 이어지고 있습니다.`)
  if (gc.prev_stage != null) {
    parts.push(`직전 ${gc.prev_stage}단계에서 전환됐습니다.`)
  }
  parts.push(`방법론상 ${gc.phase} 국면으로 분류됩니다.`)
  return parts.join(' ')
}
