import { useState } from 'react'
import { fetchRegimeTrajectory } from '../api.js'
import { useFetch } from '../lib/useFetch.js'
import { buildTrajectory } from '../lib/regimeTrajectory.js'

// 국면 이동 궤적(족적) — 같은 경기×심리 매트릭스 위에 최근 N개월 국면 이동을 트레일로 남긴다.
// 판정(cs/ss/regime)은 백엔드 엔진이 결정적으로 재현(과거 지표 → judge_regime), 여기선 표시만.
// 색: 과거=회색(저opacity)→현재=주황(--c-emph 강조), 화살표=전환/최근 방향 — 가격 방향색·경보색 금지.
// 자체 조회(환각 차단)·독립 실패 격리(궤적 실패해도 게이지 정상). 예측 아님·면책 고정.

// 기간 옵션(개월) — 백엔드 clamp 1..60 과 정합. 기본 36(3년).
const RANGES = [
  { months: 12, label: '1년' },
  { months: 24, label: '2년' },
  { months: 36, label: '3년' },
]

// "2024-01-01" → "2024.01"(캡션용). 잘못된 값은 원문 그대로(graceful).
function ym(date) {
  return typeof date === 'string' && date.length >= 7 ? date.slice(0, 7).replace('-', '.') : date
}

export default function RegimeTrajectory() {
  const [months, setMonths] = useState(36)
  const { data, loading, error, reload } = useFetch(() => fetchRegimeTrajectory(months), [months])

  const raw = data?.points ?? []
  const { points, pathD } = buildTrajectory(raw)
  const current = points.length > 0 ? points[points.length - 1] : null
  const fearGreedMissing = (data?.partial_failure ?? []).includes('fear_greed')

  return (
    <section className="rtraj" aria-label="국면 이동 궤적">
      <div className="rtraj__head">
        <h3 className="rtraj__title">국면 이동 궤적</h3>
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

      {loading ? (
        <div className="rtraj__state">국면 궤적 불러오는 중…</div>
      ) : error ? (
        <div className="rtraj__state">
          궤적을 불러오지 못했습니다.
          <button type="button" className="refresh rtraj__retry" onClick={reload}>
            ↻ 재시도
          </button>
        </div>
      ) : !data?.available || points.length === 0 ? (
        <div className="rtraj__state">{data?.note || '표시할 국면 궤적이 없습니다.'}</div>
      ) : (
        <>
          <svg
            className="rtraj__svg"
            viewBox="0 0 100 100"
            role="img"
            aria-label={`최근 ${data.months}개월 국면 이동 궤적`}
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

            {/* 연속 트레일(균일 회색 walk) */}
            {pathD && <path className="rtraj__trail" d={pathD} fill="none" />}

            {/* 방향 화살표 — 국면 전환·최근 세그먼트에만(과밀 방지) */}
            {points.map((p, i) => {
              if (i === 0) return null
              if (!p.isTransition && !p.isLast) return null
              const a = points[i - 1]
              return (
                <line
                  key={`seg-${i}`}
                  className="rtraj__seg"
                  x1={a.x}
                  y1={a.y}
                  x2={p.x}
                  y2={p.y}
                  markerEnd="url(#rtraj-arrow)"
                />
              )
            })}

            {/* 월별 점 — 과거 회색(저opacity)→현재 주황 */}
            {points.map((p, i) => (
              <circle
                key={`dot-${i}`}
                className={`rtraj__dot ${p.isLast ? 'rtraj__dot--current' : ''}`}
                cx={p.x}
                cy={p.y}
                r={p.isLast ? 2.8 : 1.7}
                opacity={p.opacity}
              />
            ))}

            {/* 현재 지점 라벨(월·국면) */}
            {current && (
              <text
                className="rtraj__label"
                x={current.x}
                y={current.y - 4}
                textAnchor={current.x > 70 ? 'end' : current.x < 30 ? 'start' : 'middle'}
              >
                {ym(current.date)} · {current.regime}
              </text>
            )}
          </svg>

          <p className="rtraj__legend">
            <span className="rtraj__legend-item">
              <span className="rtraj__swatch rtraj__swatch--past" aria-hidden="true" /> 과거
            </span>
            <span className="rtraj__legend-item">
              <span className="rtraj__swatch rtraj__swatch--now" aria-hidden="true" /> 현재
            </span>
            <span className="rtraj__legend-item">→ 국면 전환·최근</span>
            <span className="rtraj__legend-range">
              {ym(raw[0]?.date)} → {ym(raw[raw.length - 1]?.date)} · {data.months}개월
            </span>
          </p>

          {fearGreedMissing && (
            <p className="rtraj__note">
              공포탐욕지수(CNN) 일부 결측 — 심리축은 VIX 로 판정했습니다.
            </p>
          )}

          <p className="rtraj__disc">
            국면은 과거 지표를 판정 엔진으로 재현한 결과(결정적 계산)이며 미래 예측이 아닙니다. 투자 판단은
            본인 책임입니다.
          </p>
        </>
      )}
    </section>
  )
}
