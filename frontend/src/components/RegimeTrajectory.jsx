import { useState } from 'react'
import { fetchRegimeTrajectory } from '../api.js'
import { useFetch } from '../lib/useFetch.js'
import { buildRegimePath, regimeMarkerPos, stopLabelGroups } from '../lib/regimeTrajectory.js'

// 시장 국면 사분면(통합) — 같은 경기×심리 매트릭스 하나에 **과거 이동 경로**(회색·단순 경로)와
// **라이브 현재 판정**(주황 마커+활성 셀 음영)을 함께 담는다. 정적 판정 사분면을 흡수(중복 제거).
// 판정(cs/ss/regime)은 백엔드 엔진이 결정(과거=history 재현, 현재=live 실시간). 여기선 표시만.
// 색: 과거=회색(흐림)·현재=주황(--c-emph) — 가격 방향색·경보색 금지. 예측 아님·면책 고정.
//
// props.live(옵셔널) = {cs, ss, regime, cash, confidence, cycleSign, sentimentSign} — RegimeGauge 의
//   라이브 판정. 없으면(하위호환) 경로만 그리고 마지막 정차점을 현재로 강조(기존 동작).

const RANGES = [
  { months: 12, label: '1년' },
  { months: 24, label: '2년' },
  { months: 36, label: '3년' },
]

// "2024-01-01" → "24.01"(컴팩트 라벨용). 잘못된 값은 원문 그대로(graceful).
function ym(date) {
  return typeof date === 'string' && date.length >= 7 ? date.slice(2, 7).replace('-', '.') : date
}

// 정차점 반지름 — **균일**(크기로 구분하지 않는다). STOP_R < LIVE_R 로 현재만 크게.
const STOP_R = 2.6
const LIVE_R = 3.3
// 국면 → 활성 셀 4분면 좌상단(프레임 8..92, 십자 50 기준·각 42×42). 결정적 상수(프론트 재판정 아님).
const ACTIVE_CELL = {
  회복: { x: 8, y: 8 },
  확장: { x: 50, y: 8 },
  수축: { x: 8, y: 50 },
  과열: { x: 50, y: 50 },
}

export default function RegimeTrajectory({ live = null }) {
  const [months, setMonths] = useState(24)
  const { data, loading, error, reload } = useFetch(() => fetchRegimeTrajectory(months), [months])

  const raw = data?.points ?? []
  const { stops, pathD } = buildRegimePath(raw)
  const lastStop = stops.length > 0 ? stops[stops.length - 1] : null
  const fearGreedMissing = (data?.partial_failure ?? []).includes('fear_greed')

  const hasLive = !!live
  const livePos = hasLive ? regimeMarkerPos(live.cs, live.ss) : null
  const activeCell = hasLive ? ACTIVE_CELL[live.regime] : null
  // 라이브가 있으면 마지막 정차점은 '현재'가 아니라 확정 최근월(회색) — 강조는 라이브 마커가 담당.
  const legacyCurrent = !hasLive ? lastStop : null
  const pathAvailable = stops.length > 0
  // 사분면은 라이브가 있으면(현재 위치) 항상 그린다. 라이브 없으면 경로가 있어야 그린다(기존).
  const showQuadrant = hasLive || (data?.available && pathAvailable)
  // 라이브 마커와 경로 종착점(확정월)이 다른 좌표면 파선 브릿지로 '확정월→이번달' 연결.
  const showBridge = hasLive && lastStop && (lastStop.x !== livePos.x || lastStop.y !== livePos.y)
  // 정차점 월 라벨 소스 — 라이브 있으면 **라이브 마커 좌표(현재 셀)의 정차점은 제외**(그 자리는
  //   '현재·{국면}' 콜아웃이 담당 → 안정 국면에서 회색 월 라벨이 콜아웃과 겹치는 문제 해소). 라이브
  //   없으면 레거시 현재(마지막 정차점)를 특수 라벨이 담당하므로 제외.
  const labelSource = hasLive
    ? stops.filter((s) => s.x !== livePos.x || s.y !== livePos.y)
    : stops.filter((s) => s !== legacyCurrent)

  return (
    <section className="rtraj" aria-label="시장 국면 사분면(경기×심리)">
      <div className="rtraj__head">
        <h3 className="rtraj__title">국면 이동 (경기 × 심리)</h3>
        <div className="rtraj__range" role="group" aria-label="기간 선택">
          {RANGES.map((r) => (
            <button
              key={r.months}
              type="button"
              className="rtraj__range-btn"
              aria-pressed={months === r.months}
              onClick={() => setMonths(r.months)}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {!showQuadrant ? (
        loading ? (
          <div className="rtraj__state">국면 궤적 불러오는 중…</div>
        ) : error ? (
          <div className="rtraj__state">
            궤적을 불러오지 못했습니다.
            <button type="button" className="refresh rtraj__retry" onClick={reload}>
              ↻ 재시도
            </button>
          </div>
        ) : (
          <div className="rtraj__state">{data?.note || '표시할 국면 궤적이 없습니다.'}</div>
        )
      ) : (
        <>
          <svg
            className="rtraj__svg"
            viewBox="0 0 100 100"
            role="img"
            aria-label="경기×심리 국면 사분면 — 현재 위치 + 최근 이동 경로"
          >
            <defs>
              <marker
                id="rtraj-arrow"
                viewBox="0 0 10 10"
                refX="8"
                refY="5"
                markerWidth="5"
                markerHeight="5"
                orient="auto-start-reverse"
              >
                <path className="rtraj__arrow" d="M0 0 L10 5 L0 10 z" />
              </marker>
            </defs>

            {/* 사분면 배경 — 프레임 + 중앙 십자(경기0/심리0 경계) */}
            <rect className="rtraj__frame" x="8" y="8" width="84" height="84" rx="2" />
            {/* 활성 셀 음영 — 라이브 현재 국면의 사분면 1칸(주황 소프트, 경로·마커보다 뒤) */}
            {activeCell && (
              <rect
                className="rtraj__cellfill"
                x={activeCell.x}
                y={activeCell.y}
                width="42"
                height="42"
              />
            )}
            <line className="rtraj__cross" x1="50" y1="8" x2="50" y2="92" />
            <line className="rtraj__cross" x1="8" y1="50" x2="92" y2="50" />

            {/* 셀 이름(좌상 회복·우상 확장·좌하 수축·우하 과열) */}
            <text className="rtraj__cell" x="29" y="30">회복</text>
            <text className="rtraj__cell" x="71" y="30">확장</text>
            <text className="rtraj__cell" x="29" y="72">수축</text>
            <text className="rtraj__cell" x="71" y="72">과열</text>

            {/* 축 극 라벨 */}
            <text className="rtraj__axis" x="50" y="5">경기 양호</text>
            <text className="rtraj__axis" x="50" y="99">경기 악화</text>
            <text className="rtraj__axis rtraj__axis--l" x="2" y="51">공포</text>
            <text className="rtraj__axis rtraj__axis--r" x="98" y="51">탐욕</text>

            {/* 과거 이동 경로 — 정차점 잇는 폴리라인 하나 + 끝점 화살표 하나(과밀 제거) */}
            {pathD && (
              <path className="rtraj__trail" d={pathD} fill="none" markerEnd="url(#rtraj-arrow)" />
            )}

            {/* 정차점 — 균일 크기. 라이브 있으면 전부 회색(현재는 라이브 마커), 없으면 마지막=현재 주황. */}
            {stops.map((s, i) => (
              <circle
                key={`stop-${i}`}
                className={`rtraj__dot ${s === legacyCurrent ? 'rtraj__dot--current' : ''}`}
                cx={s.x}
                cy={s.y}
                r={STOP_R}
                opacity={s.opacity}
              />
            ))}

            {/* 정차점 월 라벨(시작월) — **같은 좌표(재방문 셀)는 한 라벨로 모아** ", " 로 잇는다(겹침 방지).
                위/아래 절반 바깥 배치. 레거시 현재점(라이브 없음)은 별도 강조 라벨이라 그룹에서 제외. */}
            {stopLabelGroups(labelSource).map(
              (g, i) => (
                <text
                  key={`lbl-${i}`}
                  className="rtraj__stoplabel"
                  x={g.x}
                  y={g.y < 50 ? g.y - 3.6 : g.y + 5.4}
                  textAnchor={g.x > 70 ? 'end' : g.x < 30 ? 'start' : 'middle'}
                  opacity={g.opacity}
                >
                  {g.startDates.map(ym).join(', ')}
                </text>
              ),
            )}

            {/* (라이브 없음) 마지막 정차점 강조 라벨(월·국면) */}
            {legacyCurrent && (
              <text
                className="rtraj__label"
                x={legacyCurrent.x}
                y={legacyCurrent.y < 50 ? legacyCurrent.y - 4 : legacyCurrent.y + 6}
                textAnchor={
                  legacyCurrent.x > 70 ? 'end' : legacyCurrent.x < 30 ? 'start' : 'middle'
                }
              >
                {ym(legacyCurrent.endDate)} · {legacyCurrent.regime}
              </text>
            )}

            {/* 확정월 → 라이브 현재 브릿지(좌표 다를 때만) */}
            {showBridge && (
              <line
                className="rtraj__bridge"
                x1={lastStop.x}
                y1={lastStop.y}
                x2={livePos.x}
                y2={livePos.y}
              />
            )}

            {/* 라이브 현재 마커(주황+흰 링+펄스 링) + 콜아웃 */}
            {hasLive && (
              <>
                <circle className="rtraj__live-pulse" cx={livePos.x} cy={livePos.y} r={LIVE_R} />
                <circle className="rtraj__live-dot" cx={livePos.x} cy={livePos.y} r={LIVE_R} />
                <text
                  className="rtraj__live-label"
                  x={livePos.x}
                  y={livePos.y < 50 ? livePos.y - 4.4 : livePos.y + 6.6}
                  textAnchor={livePos.x > 70 ? 'end' : livePos.x < 30 ? 'start' : 'middle'}
                >
                  현재 · {live.regime}
                </text>
              </>
            )}
          </svg>

          {/* 경기/심리 상태 readout(정적 사분면에서 이관) */}
          {hasLive && (
            <p className="rtraj__pos">
              경기: <strong>{live.cycleSign}</strong> · 심리: <strong>{live.sentimentSign}</strong>
            </p>
          )}

          <p className="rtraj__legend">
            {(hasLive || legacyCurrent) && (
              <span className="rtraj__legend-item">
                <span className="rtraj__swatch rtraj__swatch--now" aria-hidden="true" /> 현재
              </span>
            )}
            {pathAvailable && (
              <>
                <span className="rtraj__legend-item">
                  <span className="rtraj__swatch rtraj__swatch--past" aria-hidden="true" /> 과거 경로
                </span>
                <span className="rtraj__legend-item">→ 이동 방향</span>
                <span className="rtraj__legend-range">
                  {ym(raw[0]?.date)} → {ym(raw[raw.length - 1]?.date)} · {data.months}개월
                </span>
              </>
            )}
          </p>

          {/* 라이브만 있고 경로 없음(history 로딩/실패) — 현재 위치만 표시 안내 */}
          {hasLive && !pathAvailable && (
            <p className="rtraj__note">
              {loading
                ? '이동 경로 불러오는 중… (현재 위치만 표시)'
                : '이동 경로를 불러오지 못했습니다 — 현재 위치만 표시합니다.'}
            </p>
          )}

          {fearGreedMissing && (
            <p className="rtraj__note">
              공포탐욕지수(CNN) 일부 결측 — 심리축은 VIX 로 판정했습니다.
            </p>
          )}

          <p className="rtraj__disc">
            국면은 지표를 판정 엔진으로 산출한 결과(결정적 계산)이며 미래 예측이 아닙니다. 투자 판단은
            본인 책임입니다.
          </p>
        </>
      )}
    </section>
  )
}
