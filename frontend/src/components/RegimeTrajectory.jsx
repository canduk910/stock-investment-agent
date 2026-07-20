import { useState } from 'react'
import { fetchRegimeTrajectory } from '../api.js'
import { useFetch } from '../lib/useFetch.js'
import {
  buildSampledTrajectory,
  regimeMarkerPos,
  labelYearShades,
  placeLabelY,
} from '../lib/regimeTrajectory.js'

// 시장 국면 사분면(통합) — 같은 경기×심리 매트릭스 하나에 **표본별 개별 이동 점**(회색)과 **라이브 현재
// 판정**(주황 마커+활성 셀 음영)을 함께 담는다. 정적 판정 사분면을 흡수(중복 제거). 표본은 백엔드가
// 범위별로 골라(분기/반기/연) 소수라, 각 표본을 개별 점으로 표시(같은 국면 반복은 작은 오프셋으로 분리).
// 판정(cs/ss/regime)은 백엔드 엔진이 결정(과거=history 재현, 현재=live 실시간). 여기선 표시만.
// 색: 과거=회색(흐림)·현재=주황(--c-emph) — 가격 방향색·경보색 금지. 예측 아님·면책 고정.
//
// props.live(옵셔널) = {cs, ss, regime, cash, confidence, cycleSign, sentimentSign} — RegimeGauge 의
//   라이브 판정. 없으면(하위호환) 표본 점만 그리고 마지막 표본을 현재로 강조(기존 동작).

const RANGES = [
  { months: 12, label: '1년' },
  { months: 24, label: '2년' },
  { months: 36, label: '3년' },
]

// 표본 간격 코드(백엔드 `interval`) → 한글 라벨. 범례에 표시해 "무슨 기준으로 찍히나"를 명확히 한다
// (1년=분기·2년=반기·3년=연). 백엔드 macro.regime_history.trajectory_step 과 코드 SSOT.
const INTERVAL_LABEL = {
  monthly: '월별',
  quarterly: '분기별',
  semiannual: '반기별',
  annual: '연별',
}

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
  const fearGreedMissing = (data?.partial_failure ?? []).includes('fear_greed')

  const hasLive = !!live
  const livePos = hasLive ? regimeMarkerPos(live.cs, live.ss) : null
  const activeCell = hasLive ? ACTIVE_CELL[live.regime] : null
  // 표본별 개별 노드 궤적 — 같은 칸 반복은 오프셋, 가장 최근 표본이 라이브 칸이면 라이브가 대표(defer).
  const { visible, pathD, deferLast } = buildSampledTrajectory(raw, livePos)
  // 라이브 없으면 마지막 표본을 '현재'로 강조(하위호환) — 있으면 라이브 마커가 현재.
  const legacyCurrent = !hasLive && visible.length > 0 ? visible[visible.length - 1] : null
  const lastVisible = visible.length > 0 ? visible[visible.length - 1] : null
  const pathAvailable = visible.length > 0
  // 사분면은 라이브가 있으면(현재 위치) 항상 그린다. 라이브 없으면 표시 노드가 있어야(기존).
  const showQuadrant = hasLive || (data?.available && pathAvailable)
  // 최근 표본이 라이브와 다른 칸(defer 아님)이면 그 점→라이브 파선 브릿지로 '확정월→이번달' 연결.
  const showBridge =
    hasLive &&
    !deferLast &&
    lastVisible &&
    (Math.abs(lastVisible.x - livePos.x) > 0.01 || Math.abs(lastVisible.y - livePos.y) > 0.01)
  // 라벨 대상: 표시 노드 전부(각 표본 개별 라벨). 레거시 현재(라이브 없음)는 별도 강조 라벨이라 제외.
  const labelNodes = legacyCurrent ? visible.filter((nd) => nd !== legacyCurrent) : visible

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

            {/* 이동 경로 — 표시 노드 잇는 폴리라인 하나 + 끝점 화살표 하나(defer 면 라이브로 종결) */}
            {pathD && (
              <path className="rtraj__trail" d={pathD} fill="none" markerEnd="url(#rtraj-arrow)" />
            )}

            {/* 표본 점 — 각 표본 개별(균일 크기). 라이브 있으면 전부 회색(현재는 라이브 마커), 없으면 마지막=현재 주황. */}
            {visible.map((nd, i) => (
              <circle
                key={`dot-${i}`}
                className={`rtraj__dot ${nd === legacyCurrent ? 'rtraj__dot--current' : ''}`}
                cx={nd.x}
                cy={nd.y}
                r={STOP_R}
                opacity={nd.opacity}
              />
            ))}

            {/* 표본 월 라벨 — 각 표본 개별(병합 안 함). 위/아래 절반 바깥 배치. 레거시 현재점(라이브 없음)은
                별도 강조 라벨이라 제외. **년도별 밝기 그라데이션**: labelYearShades 가 준 shadeLevel
                (0=과거 옅게→3=최근 짙게)을 `--y{n}` 클래스로 매핑(색은 styles.css 토큰). */}
            {labelYearShades(labelNodes).map((nd, i) => (
              <text
                key={`lbl-${i}`}
                className={`rtraj__stoplabel rtraj__stoplabel--y${nd.shadeLevel}`}
                x={nd.x}
                y={placeLabelY(nd.y, 3.6, 5.4)}
                textAnchor={nd.x > 70 ? 'end' : nd.x < 30 ? 'start' : 'middle'}
              >
                {ym(nd.date)}
              </text>
            ))}

            {/* (라이브 없음) 마지막 표본 강조 라벨(월·국면) */}
            {legacyCurrent && (
              <text
                className="rtraj__label"
                x={legacyCurrent.x}
                y={placeLabelY(legacyCurrent.y, 4, 6)}
                textAnchor={
                  legacyCurrent.x > 70 ? 'end' : legacyCurrent.x < 30 ? 'start' : 'middle'
                }
              >
                {ym(legacyCurrent.date)} · {legacyCurrent.regime}
              </text>
            )}

            {/* 최근 표본 → 라이브 현재 브릿지(좌표 다를 때만) */}
            {showBridge && (
              <line
                className="rtraj__bridge"
                x1={lastVisible.x}
                y1={lastVisible.y}
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
                  y={placeLabelY(livePos.y, 4.4, 6.6)}
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
                  {INTERVAL_LABEL[data.interval] ? ` · ${INTERVAL_LABEL[data.interval]}` : ''}
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
