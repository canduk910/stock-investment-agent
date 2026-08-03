import { useMemo, useState } from 'react'
import { fetchScreener } from '../api.js'
import { useFetch } from '../lib/useFetch.js'
import { stageGlyph } from '../lib/grandCycle.js'
import { num, signedNum } from '../lib/format.js'
import SegmentedControl from './SegmentedControl.jsx'

// 대순환(고지로) 단계 기반 후보 종목 스크리너 — 한국시장 전체 보통주(DB 캐시)를 대순환 단계로 스캔한
//   결과를 서빙한다. 판정(단계)은 백엔드 엔진(코드)이 확정, 여기선 표시·필터·정렬만.
//   ★캐시 모드엔 현재가/등락률/시총이 없다(무캐시·확정 stage/band만) — 시세는 카드 클릭 시 종목 상세가
//    라이브 조회한다. 따라서 카드는 stage 중심(종목명·코드·시장·단계 배지·밴드)이고 등락 칩·시총은 없다.
//   색: 단계 배지=주황 강조(--c-emph)+방향 글리프. 경보색·hex 금지.
//
// props: onOpenStock(ticker, name) — 후보 카드 클릭 시 종목 상세로 전환(RightPanel openStock SSOT). 옵셔널.
// 조회: useFetch(fetchScreener(market,'cached')) 자체 조회 — market 변경 시만 재조회. 단계 필터·표시
//       상한은 클라이언트(재조회 0). 전체 유니버스라 필터 후에도 많을 수 있어 표시 상한(60)+"외 N종목".
// 안전: 매매 API 없음(조회·표시만). 단계는 규칙 엔진 결과이고 매수·매도 판정이 아니다(하단 면책 고정).

// 시장 선택기 — kospi200 은 cached(전체 보통주 스캔) 미지원이라 제외(전체/코스피/코스닥).
const MARKETS = [
  { key: 'all', label: '전체' },
  { key: 'kospi', label: '코스피' },
  { key: 'kosdaq', label: '코스닥' },
]

// candidate.market → 표시 라벨. cached 는 대문자 "KOSPI"/"KOSDAQ"(stock_master 원값·screener-be 확정).
//   대소문자 무관 조회(방어)·미지의 값은 원문 그대로. live 폴백엔 per-item market 이 없어(undefined) 생략.
const MARKET_LABEL = { KOSPI: '코스피', KOSDAQ: '코스닥' }
function marketLabel(m) {
  if (!m) return ''
  return MARKET_LABEL[String(m).toUpperCase()] ?? m
}

// 단계 필터(클라이언트·재조회 없음). 기본 상승국면(1 안정상승 · 6 상승진입). stages=null 이면 전체.
const STAGE_FILTERS = [
  { key: 'rising', label: '상승국면', stages: [1, 6] },
  { key: 'all', label: '전체 단계', stages: null },
  { key: 's1', label: '1단계', stages: [1] },
  { key: 's2', label: '2단계', stages: [2] },
  { key: 's3', label: '3단계', stages: [3] },
  { key: 's4', label: '4단계', stages: [4] },
  { key: 's5', label: '5단계', stages: [5] },
  { key: 's6', label: '6단계', stages: [6] },
]

// 전체 유니버스라 필터 후 후보가 수백일 수 있어 상위 N개만 카드로 렌더(나머지는 "외 N종목"으로 요약).
const DISPLAY_CAP = 60

// 정렬: 단계 오름차순 → 같은 단계는 밴드폭(band_width_pct) 내림차순(추세 강도). 결측 밴드·판정보류(stage
//   null)는 뒤로. 판정=백엔드, 여기선 표시 순서만(원값 불변).
function cmpCandidate(a, b) {
  const sa = a.stage ?? 99
  const sb = b.stage ?? 99
  if (sa !== sb) return sa - sb
  const na = a.band_width_pct == null
  const nb = b.band_width_pct == null
  if (na && nb) return 0
  if (na) return 1
  if (nb) return -1
  return b.band_width_pct - a.band_width_pct
}

export default function ScreenerPanel({ onOpenStock }) {
  const [market, setMarket] = useState('all') // 시장 선택 — 변경 시 재조회(useFetch deps)
  const [filter, setFilter] = useState('rising') // 단계 필터(클라이언트) — 기본 상승국면(1·6)
  // scope=cached 고정(전체 보통주 스캔 결과). DB 비었으면 백엔드가 scope:'live' 로 자동 폴백해 내려준다.
  const { data, loading, error, reload } = useFetch(() => fetchScreener(market, 'cached'), [market])

  // catalog(6단계 라벨 SSOT — 백엔드가 내려줌) → stage → {name, phase} 조회 맵.
  // 프론트가 단계 이름을 복제하지 않도록 백엔드 카탈로그로 라벨/방향을 조회(useMemo 로 data 변경 시만 재구성).
  const stageMeta = useMemo(() => {
    const m = new Map()
    for (const s of data?.catalog?.stages || []) m.set(s.stage, s)
    return m
  }, [data])

  const candidates = data?.candidates || [] // 서버가 스캔한 전체 후보(단계 판정 포함, 전 단계)
  const active = STAGE_FILTERS.find((f) => f.key === filter) || STAGE_FILTERS[0] // 현재 필터 정의
  // 필터에 stages 목록이 있으면 그 단계만, null('전체 단계')이면 전부(클라이언트 필터 — 재조회 없음).
  const sorted = useMemo(() => {
    const base = active.stages
      ? candidates.filter((c) => active.stages.includes(c.stage))
      : candidates
    return [...base].sort(cmpCandidate)
  }, [candidates, active])
  const shown = sorted.slice(0, DISPLAY_CAP) // 상위 N개만 카드로
  const hidden = sorted.length - shown.length // 상한 초과분("외 N종목")
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
              일부 종목은 스캔 중 일시 조회 실패로 단계가 비어 있어요({partial.length}종목).
            </div>
          )}
          <div className="screener__count">
            {sorted.length}종목 · {active.label}
            {hidden > 0 && ` · 상위 ${DISPLAY_CAP} 표시 (외 ${hidden}종목)`}
          </div>
          {sorted.length === 0 ? (
            <div className="popup__state">
              해당 단계의 후보가 없어요. 다른 단계나 시장을 선택해 보세요.
            </div>
          ) : (
            <ul className="wl__list">
              {shown.map((c) => (
                <ScreenerRow
                  key={c.ticker}
                  c={c}
                  meta={stageMeta.get(c.stage)}
                  onOpenStock={onOpenStock}
                />
              ))}
            </ul>
          )}
        </>
      )}

      <p className="screener__disclaimer">
        대순환 단계는 이동평균 배열 기반 기술적 참고입니다 · 매수·매도 판정이 아니며 투자 책임은
        본인에게 있습니다.
      </p>
    </div>
  )
}

// 후보 종목 한 줄 — 관심종목(.wl__*) 카드 스타일 재사용. 정보 영역만 클릭 가능(상세 이동).
//   ★캐시 모드라 현재가/등락 칩/시총이 없다 — stage 중심(종목명·코드·시장·단계 배지·밴드).
function ScreenerRow({ c, meta, onOpenStock }) {
  const clickable = !!onOpenStock // onOpenStock 없으면 순수 표시(클릭 비활성·옵셔널)
  const openDetail = () => onOpenStock?.(c.ticker, c.name ?? c.ticker) // 상세 전환(종목명 전달)
  const hasStage = c.stage != null // 단계 판정 성공 여부(봉 부족·조회 실패 시 null)
  // 배지 라벨 — 백엔드 카탈로그(meta) 이름 우선, 없으면 서버가 준 stage_name 폴백.
  const stageLabel = hasStage ? `${c.stage}단계 · ${meta?.name ?? c.stage_name ?? ''}` : ''
  const mkt = marketLabel(c.market)

  return (
    <li className="wl__row">
      {/* 정보 영역(row-top)만 클릭·키보드 접근(role=button·Enter/Space). clickable 아니면 속성 없이 순수 표시 */}
      <div
        className={`wl__row-top${clickable ? ' wl__row-top--clickable' : ''}`}
        {...(clickable
          ? {
              role: 'button',
              tabIndex: 0,
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
    </li>
  )
}
