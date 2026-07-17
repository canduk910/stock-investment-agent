import { fetchMacroRegime } from '../api.js'
import { useFetch } from '../lib/useFetch.js'
import MacroIndicatorCards from './MacroIndicatorCards.jsx'

// 2×2 사분면 셀 — 세로축 경기(위 양호/아래 악화) · 가로축 심리(좌 공포/우 탐욕).
// 배치: 회복=좌상, 확장=우상, 수축=좌하, 과열=우하.
// 렌더 순서(2열 grid) = 회복 → 확장 → 수축 → 과열. 엔진 classify 의 모서리 해석과 동일.
const QUADRANT_CELLS = ['회복', '확장', '수축', '과열']

// 국면별 짧은 해설(결정적·정적, LLM 아님) — 축 조합의 의미를 한 줄로.
const REGIME_DESC = {
  회복: '펀더멘털 개선 + 시장 공포 — 저가 매수 초입',
  확장: '펀더멘털 양호 — 건강한 성장 국면',
  과열: '펀더멘털 대비 과도한 탐욕 — 고평가 위험',
  수축: '펀더멘털 악화 + 공포 — 급락·투매 국면',
}

// 신뢰도 배지 톤 — high=남색 / medium=파랑 / low=회색. 색은 CSS 토큰에서만.
const CONFIDENCE_META = {
  high: { label: '높음', className: 'confidence--high' },
  medium: { label: '보통', className: 'confidence--medium' },
  low: { label: '낮음', className: 'confidence--low' },
}

// 엔진 내부 지표 키 → 사람이 읽는 라벨(누락 안내용). indicatorMeta 와 별개(엔진 키 체계).
const ENGINE_KEY_LABEL = {
  yield_spread: '장단기 금리차',
  hy_spread: 'HY 신용스프레드',
  vix: 'VIX',
  fear_greed: '공포탐욕지수',
}

export default function RegimeGauge() {
  const { data, loading, error } = useFetch(fetchMacroRegime)

  if (loading) {
    return (
      <section className="gauge gauge--state">
        <span className="gauge__badge">W07</span>
        <span className="gauge__state-text">국면 판정 중…</span>
      </section>
    )
  }

  if (error) {
    return (
      <section className="gauge gauge--state gauge--state-error">
        <span className="gauge__badge">W07</span>
        <span className="gauge__state-text">국면 조회 실패: {error}</span>
        <button className="refresh" onClick={load}>
          ↻ 재시도
        </button>
      </section>
    )
  }

  if (!data) return null

  const {
    regime,
    recommended_cash_ratio,
    confidence,
    axes = {},
    indicator_breakdown = [],
    vix_panic = false,
    missing_indicators = [],
  } = data

  const conf = CONFIDENCE_META[confidence] ?? CONFIDENCE_META.low
  const cycleSign = axes?.cycle?.sign ?? '중립'
  const sentimentSign = axes?.sentiment?.sign ?? '중립'
  const missingLabels = missing_indicators.map((k) => ENGINE_KEY_LABEL[k] ?? k)

  // 사분면 위 실제 위치 마커 — 축 점수(-2..+2)를 평면 좌표로. 중립(0)이면 정중앙.
  // x: 심리(좌 공포 → 우 탐욕), y: 경기(위 양호 → 아래 악화). 셀 밖으로 안 나가게 12~88%.
  const cycleScore = axes?.cycle?.score ?? 0
  const sentimentScore = axes?.sentiment?.score ?? 0
  const markerX = 12 + ((sentimentScore + 2) / 4) * 76
  const markerY = 12 + ((2 - cycleScore) / 4) * 76

  // ⑤ 손실경고 — 수축(급락장 매수 제안) 또는 VIX 패닉이면 남색 강조 배너.
  const showLossWarning = regime === '수축' || vix_panic === true

  return (
    <section className="gauge">
      <div className="gauge__head">
        <span className="gauge__badge">W07</span>
        <h2 className="gauge__title">시장 국면 판정</h2>
        {vix_panic && (
          <span className="panic-chip" title="VIX 35 초과 — 극단 변동성">
            ⚠ VIX 패닉
          </span>
        )}
        <span className={`confidence ${conf.className}`}>신뢰도 {conf.label}</span>
      </div>

      {/* ⑤ 손실경고 배너 — 역발상 매수 제안의 위험을 남색으로 강조 */}
      {showLossWarning && (
        <div className="banner banner--loss" role="alert">
          <span className="banner__glyph" aria-hidden="true">
            ⚠
          </span>
          <span>
            <strong>역발상 관점</strong>: 급락장 매수 제안 — 손실 위험이 큽니다. 투자 판단은
            본인 책임(면허 있는 자문 아님).
          </span>
        </div>
      )}

      {/* ① 2×2 사분면 — 세로축 경기(위 양호/아래 악화), 가로축 심리(좌 공포/우 탐욕) */}
      <div className="quadrant" aria-label="경기·심리 2축 국면 매트릭스">
        <div className="quadrant__xhead">
          <span className="quadrant__pole">공포</span>
          <span className="quadrant__axis">심리</span>
          <span className="quadrant__pole">탐욕</span>
        </div>

        <div className="quadrant__yhead">
          <span className="quadrant__pole">양호</span>
          <span className="quadrant__axis">경기</span>
          <span className="quadrant__pole">악화</span>
        </div>

        <div className="quadrant__grid" role="list" aria-label="시장 국면 사분면">
          {QUADRANT_CELLS.map((cellRegime) => {
            const active = cellRegime === regime
            return (
              <div
                key={cellRegime}
                role="listitem"
                className={`qcell ${active ? 'qcell--active' : ''}`}
                aria-current={active ? 'true' : undefined}
              >
                <span className="qcell__name">{cellRegime}</span>
              </div>
            )
          })}
          {/* 실제 축 위치 마커 — 강조 셀 + 이 점으로 "정확히 어디인지"까지 보여준다 */}
          <div
            className="quadrant__marker"
            style={{ left: `${markerX}%`, top: `${markerY}%` }}
            aria-hidden="true"
          >
            <span className="quadrant__marker-dot" />
          </div>
        </div>

        <div className="quadrant__pos">
          경기: <strong>{cycleSign}</strong> · 심리: <strong>{sentimentSign}</strong>
        </div>
      </div>

      {/* 국면 해설 — 축 조합의 의미(결정적 정적 텍스트) */}
      <p className="regime-desc">
        <strong className="regime-desc__name">{regime}</strong>
        {REGIME_DESC[regime] ? ` · ${REGIME_DESC[regime]}` : ''}
      </p>

      <div className="gauge__body">
        {/* ② 권장 현금비중 큰 숫자 — 역발상 값 자동 반영(엔진 REGIME_PARAMS 단일 출처) */}
        <div className="cash-ratio">
          <div className="cash-ratio__value">
            {recommended_cash_ratio}
            <span className="cash-ratio__unit">%</span>
          </div>
          <div className="cash-ratio__label">권장 현금비중</div>
        </div>
      </div>

      {/* ④ 판정 근거 4지표 카드 — 값 + 구간(양호/중립/악화·탐욕/중립/공포) + 축. 클릭 → 최근 1년 히스토리.
          국면 판정에 실제 쓰인 수치를 표면화한다(수치는 데이터, 판정은 코드/엔진). */}
      <MacroIndicatorCards breakdown={indicator_breakdown} />

      {/* ⑥ 부분 실패 — 누락 지표는 남은 지표로만 판정했음을 안내 */}
      {missingLabels.length > 0 && (
        <div className="banner banner--warn gauge__note">
          일부 지표 누락: {missingLabels.join(', ')} · 남은 지표로만 판정
        </div>
      )}
    </section>
  )
}
