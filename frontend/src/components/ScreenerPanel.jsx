import { useMemo, useState } from 'react'
import { fetchScreener } from '../api.js'
import { useFetch } from '../lib/useFetch.js'
import { stageGlyph } from '../lib/grandCycle.js'
import { num, pct, signedNum, changeDir } from '../lib/format.js'
import SegmentedControl from './SegmentedControl.jsx'
import ChangeChip from './ChangeChip.jsx'
import Sparkline from './Sparkline.jsx'

// 대순환(고지로) 단계 기반 후보 종목 스크리너 — 한국시장 전체 보통주(DB 캐시)를 대순환 단계로 스캔한
//   결과를 서빙한다. 판정(단계·밴드)은 백엔드 엔진(코드)이 확정, 여기선 표시·필터 선택·클릭만.
//   ★백엔드가 stage 필터 + 시총 역순 정렬 + 표시 top-N enrich(가격·등락·PER·재무 100점·스파크)를
//    모두 마쳐 내려준다 — 프론트는 응답 순서대로 렌더하고(클라이언트 재정렬 없음), stage 필터는 서버
//    파라미터라 선택 시 재조회한다. 시세·재무점수 등 실데이터는 백엔드 라이브 조회(무캐시)라 프론트가
//    다시 조회하지 않고 응답 그대로 표시한다(환각 차단·최신성).
//
// props: onOpenStock(ticker, name) — 후보 카드 클릭 시 종목 상세로 전환(RightPanel openStock SSOT). 옵셔널.
// 조회: useFetch(fetchScreener(market, stageFilter)) — market/stage 변경 시 재조회. 표시 상한은 백엔드.
// 안전: 매매 API 없음(조회·표시만). 단계·재무점수는 규칙 엔진 결과이고 매수·매도 판정이 아니다(하단 면책 고정).
//   색 규칙: 등락·스파크는 방향색(ChangeChip/Sparkline SSOT), 단계 배지=주황 강조 + 글리프,
//   ★재무점수·PER 에는 방향색(빨/파)·경보색·초록/황색 금지 — 점수 게이지 채움은 주황(--c-emph)뿐.

// 시장 선택기 — kospi200 은 cached(전체 보통주 스캔) 미지원이라 제외(전체/코스피/코스닥).
const MARKETS = [
  { key: 'all', label: '전체' },
  { key: 'kospi', label: '코스피' },
  { key: 'kosdaq', label: '코스닥' },
]

// candidate.market → 표시 라벨. cached 는 대문자 "KOSPI"/"KOSDAQ"(stock_master 원값·screener-be 확정).
//   대소문자 무관 조회(방어)·미지의 값은 원문 그대로. live 폴백엔 per-item market 이 없을 수 있어 생략.
const MARKET_LABEL = { KOSPI: '코스피', KOSDAQ: '코스닥' }
function marketLabel(m) {
  if (!m) return ''
  return MARKET_LABEL[String(m).toUpperCase()] ?? m
}

// 단계 필터 — key = 서버 stage 파라미터 값(all | rising | 1..6). 선택 시 재조회(백엔드가 필터·정렬·enrich).
//   기본 rising(상승국면 1·6). 백엔드가 stage 로 후보를 골라 시총 역순 정렬 후 top-N 을 enrich 해 준다.
const STAGE_FILTERS = [
  { key: 'rising', label: '상승국면' },
  { key: 'all', label: '전체 단계' },
  { key: '1', label: '1단계' },
  { key: '2', label: '2단계' },
  { key: '3', label: '3단계' },
  { key: '4', label: '4단계' },
  { key: '5', label: '5단계' },
  { key: '6', label: '6단계' },
]

// 재무 100점 점수 게이지 폭(%) — 점수/최대점수 를 0..100 으로 정규화(색은 CSS 가 주황 고정).
//   결측(미enrich)·비수치는 0(빈 게이지) — 방향/우열을 색으로 칠하지 않는다(폭으로만 표현).
function scoreWidth(score, maxScore) {
  const s = Number(score)
  const m = Number(maxScore) || 100
  if (!Number.isFinite(s) || m <= 0) return 0
  return Math.max(0, Math.min(100, (s / m) * 100))
}

export default function ScreenerPanel({ onOpenStock }) {
  const [market, setMarket] = useState('all') // 시장 선택 — 변경 시 재조회(useFetch deps)
  const [filter, setFilter] = useState('rising') // 단계 필터 = 서버 stage 파라미터 — 변경 시 재조회
  // 백엔드가 stage 필터 + 시총 역순 정렬 + top-N enrich 를 수행하므로 프론트는 응답을 그대로 표시한다.
  // scope 는 api.js 내부 cached 고정 — DB 비었으면 백엔드가 scope:'live' 로 자동 폴백해 내려준다.
  const { data, loading, error, reload } = useFetch(
    () => fetchScreener(market, filter),
    [market, filter],
  )

  // catalog(6단계 라벨 SSOT — 백엔드가 내려줌) → stage → {name, phase} 조회 맵.
  // 프론트가 단계 이름을 복제하지 않도록 백엔드 카탈로그로 라벨/방향을 조회(useMemo 로 data 변경 시만 재구성).
  const stageMeta = useMemo(() => {
    const m = new Map()
    for (const s of data?.catalog?.stages || []) m.set(s.stage, s)
    return m
  }, [data])

  // 재무점수 만점(분모) — score_config.max_score 소비(SSOT·백엔드 상수). 없으면 100.
  const maxScore = data?.score_config?.max_score ?? 100

  // 백엔드가 이미 stage 필터 + 시총 역순 정렬 + 표시 top-N enrich 를 마쳤다 — 응답 순서대로 렌더한다.
  const candidates = data?.candidates || []
  const active = STAGE_FILTERS.find((f) => f.key === filter) || STAGE_FILTERS[0] // 현재 필터 정의
  const total = data?.total ?? candidates.length // stage 필터 후 후보 총수(표시 top-N 이전)
  const hidden = Math.max(0, total - candidates.length) // 표시 상한 초과분("외 N종목", 음수 방지)
  const partial = data?.partial_failure || [] // 스캔 중 일봉 조회 실패로 단계가 빈 종목 목록(부분 실패 보존)

  const scope = data?.scope // 'cached' | 'live'
  const asOf = data?.as_of // 스캔 기준일(YYYY-MM-DD)
  const universe = data?.universe_size // 스캔한 전체 보통주 수

  return (
    <div className="screener">
      <div className="screener__controls">
        <div className="screener__markets" role="group" aria-label="시장 선택">
          {/* 선택기 골격은 SegmentedControl SSOT — 활성은 is-active 클래스 주입. */}
          <SegmentedControl options={MARKETS} value={market} onChange={setMarket}
            buttonClass="screener__seg" activeClass="is-active" />
        </div>
        <div className="screener__stages" role="group" aria-label="대순환 단계 필터">
          {/* 단계 필터 = 서버 파라미터(선택 시 재조회) — 백엔드가 필터·정렬·enrich. */}
          <SegmentedControl options={STAGE_FILTERS} value={filter} onChange={setFilter}
            buttonClass="screener__chip" activeClass="is-active" />
        </div>
      </div>

      {/* 상태 분기: 최초 스캔 조회 중 / 최초 조회 실패(재시도) / 결과(스캔기준·부분실패·개수·목록). 재조회
          중엔 이전 data 를 유지하므로 `&& !data` 로 최초 로딩·에러만 전면 표시(스왑 깜빡임 방지). */}
      {loading && !data ? (
        <div className="popup__state">저장된 후보 종목을 불러오는 중…</div>
      ) : error && !data ? (
        <div className="banner banner--warn">
          후보 조회에 실패했어요.{' '}
          <button type="button" className="banner__retry" onClick={reload}>
            다시 시도
          </button>
        </div>
      ) : (
        <>
          {/* 스캔 기준 표기: cached 는 스캔일 + 전체 보통주 유니버스, live 폴백은 회색 임시 안내(주황 아님). */}
          <div className="screener__scanmeta">
            {scope === 'live' ? (
              <>⚠ 전체 스캔 전 — 시총 상위 임시 표시</>
            ) : (
              <>
                {asOf ? `${asOf} 스캔 기준` : '전체 보통주 스캔 기준'}
                {universe != null && ` · 전체 보통주 ${num(universe)}종목`}
              </>
            )}
          </div>
          {partial.length > 0 && (
            <div className="screener__note">
              일부 종목은 현재가를 일시 조회하지 못했어요 — 가격·PER를 '—'로 표시({partial.length}종목).
            </div>
          )}
          <div className="screener__count">
            {total}종목 · {active.label}
            {hidden > 0 && ` · 상위 ${candidates.length} 표시 (외 ${hidden}종목)`}
          </div>
          {candidates.length === 0 ? (
            <div className="popup__state">
              해당 단계의 후보가 없어요. 다른 단계나 시장을 선택해 보세요.
            </div>
          ) : (
            <ul className="wl__list">
              {candidates.map((c) => (
                <ScreenerRow
                  key={c.ticker}
                  c={c}
                  meta={stageMeta.get(c.stage)}
                  maxScore={maxScore}
                  onOpenStock={onOpenStock}
                />
              ))}
            </ul>
          )}
        </>
      )}

      <p className="screener__disclaimer">
        대순환 단계·재무점수는 이동평균 배열·재무비율 기반 기술적/정량 참고입니다 · 매수·매도 판정이
        아니며 투자 책임은 본인에게 있습니다.
      </p>
    </div>
  )
}

// 후보 종목 한 줄 — 관심종목(.wl__*) 카드 스타일 재사용. 정보 영역(row-top)만 클릭 가능(상세 이동).
//   상단: 종목명·코드·시장 + 스파크라인 + 가격·등락 칩(라이브 enrich).
//   하단: 단계 배지 + 밴드 · PER + 재무 100점 점수 게이지(PER 오른편).
//   ★가격·등락은 방향색(ChangeChip/Sparkline), 단계는 주황+글리프, 재무점수·PER 은 방향색/경보색 금지.
function ScreenerRow({ c, meta, maxScore, onOpenStock }) {
  const clickable = !!onOpenStock // onOpenStock 없으면 순수 표시(클릭 비활성·옵셔널)
  const openDetail = () => onOpenStock?.(c.ticker, c.name ?? c.ticker) // 상세 전환(종목명 전달)
  const hasStage = c.stage != null // 단계 판정 성공 여부(봉 부족·조회 실패 시 null)
  // 배지 라벨 — 백엔드 카탈로그(meta) 이름 우선, 없으면 서버가 준 stage_name 폴백.
  const stageLabel = hasStage ? `${c.stage}단계 · ${meta?.name ?? c.stage_name ?? ''}` : ''
  const mkt = marketLabel(c.market)
  const dir = changeDir(c.change_rate) // 등락 방향(스파크·칩 공용) — 결측이면 null(회색·글리프 ─)
  // 재무점수 축 breakdown 툴팁(선택·있으면 좋음) — score_config 라벨(=fin_axes.label) 사용.
  const axisTip =
    Array.isArray(c.fin_axes) && c.fin_axes.length
      ? c.fin_axes.map((a) => `${a.label} ${a.points}/${a.max}`).join(' · ')
      : undefined

  return (
    <li className="wl__row">
      {/* 정보 영역(row-top)만 클릭·키보드 접근(role=button·Enter/Space). clickable 아니면 속성 없이 순수 표시 */}
      <div
        className={`wl__row-top${clickable ? ' wl__row-top--clickable' : ''}`}
        {...(clickable
          ? {
              role: 'button',
              tabIndex: 0,
              'aria-label': `${c.name ?? c.ticker} 종목 상세 보기`,
              onClick: openDetail,
              onKeyDown: (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  openDetail()
                }
              },
            }
          : {})}
      >
        <div className="wl__row-id">
          <span className="wl__name">{c.name ?? c.ticker}</span>
          <span className="wl__meta">{mkt ? `${c.ticker} · ${mkt}` : c.ticker}</span>
        </div>
        {/* 미니 스파크라인 — 선색=등락 방향색(dir). spark 결측이면 컴포넌트가 조용히 생략. */}
        <Sparkline points={c.spark} dir={dir} />
        {/* 가격 + 등락 칩(라이브 enrich). 미enrich(price null)면 "—" graceful. */}
        <div className="wl__row-price">
          {c.price == null ? (
            <span className="wl__fail">—</span>
          ) : (
            <>
              <span className="wl__price">{num(c.price)}원</span>
              {/* 등락 칩은 ChangeChip SSOT(방향색 클래스+글리프+부호 규칙 공용). */}
              <ChangeChip value={c.change_rate} />
            </>
          )}
        </div>
      </div>

      <div className="wl__row-bottom">
        {/* 단계 배지 = 주황 강조 + 방향 글리프(▲▼◆). 방향은 색이 아니라 글리프로(디자인 규칙).
            판정 불가(봉 부족)면 뉴트럴 회색 배지로 구분. */}
        {hasStage ? (
          <span className="badge badge--emph">
            {stageLabel} {meta ? stageGlyph(meta.phase) : ''}
          </span>
        ) : (
          <span className="badge badge--muted">판정 보류(봉 부족)</span>
        )}
        {c.band_width_pct != null && (
          <span className="screener__band">
            밴드 {signedNum(c.band_width_pct, 1)}%{c.band_direction ? ` · ${c.band_direction}` : ''}
          </span>
        )}
      </div>

      {/* PER + 재무 100점 점수(PER 오른편). ★방향색·경보색 금지 — 점수 게이지 채움은 주황(--c-emph)만. */}
      <div className="screener__metrics">
        <span className="screener__per">PER {pct(c.per, 1)}</span>
        <div className="screener__score" title={axisTip}>
          <span className="screener__score-label">재무점수</span>
          {/* 게이지 트랙은 wl__gauge 재사용(회색 트랙), 채움색은 screener 가 주황으로 소유. */}
          <div className="wl__gauge screener__score-track" aria-hidden="true">
            <span
              className="wl__gauge-fill screener__score-fill"
              style={{ width: `${scoreWidth(c.fin_score, maxScore)}%` }}
            />
          </div>
          <span className="screener__score-num">
            {c.fin_score == null ? `—/${maxScore}` : `${c.fin_score}/${maxScore}`}
          </span>
        </div>
      </div>
    </li>
  )
}
