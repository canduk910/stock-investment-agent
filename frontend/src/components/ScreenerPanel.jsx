import { useMemo, useState } from 'react'
import { fetchScreener } from '../api.js'
import { useFetch } from '../lib/useFetch.js'
import { stageGlyph } from '../lib/grandCycle.js'
import { num, signedNum } from '../lib/format.js'
import ChangeChip from './ChangeChip.jsx'

// 대순환(고지로) 단계 기반 후보 종목 스크리너 — 시총상위 유니버스를 대순환 단계로 스캔.
//   판정(단계)은 백엔드 엔진(코드)이 확정, 여기선 표시·필터만. 실데이터는 프론트가 직접 조회(환각 차단).
//   색: 단계 배지=주황 강조(--c-emph)+방향 글리프, 등락=방향색(--c-up/down). 경보색·hex 금지.
//
// props: onOpenStock(ticker, name) — 후보 카드 클릭 시 종목 상세로 전환(RightPanel openStock SSOT). 옵셔널.
// 조회: useFetch(fetchScreener(market,30)) 자체 조회 — market 변경 시만 재조회. 단계 필터는 클라이언트(재조회 0).
// 안전: 매매 API 없음(조회·표시만). 단계는 규칙 엔진 결과이고 매수·매도 판정이 아니다(하단 면책 고정).

const MARKETS = [
  { key: 'all', label: '전체' },
  { key: 'kospi', label: '코스피' },
  { key: 'kosdaq', label: '코스닥' },
  { key: 'kospi200', label: '코스피200' },
]

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

function marketCapJo(v) {
  // KIS stck_avls 는 억원 단위 → 조원(1조 = 10,000억)으로 표시(라이브 확인: 삼성 14,586,465억 = 1,459조).
  if (v == null) return '—'
  return `${num(v / 10000)}조`
}

export default function ScreenerPanel({ onOpenStock }) {
  const [market, setMarket] = useState('all') // 시장 선택 — 변경 시 재조회(useFetch deps)
  const [filter, setFilter] = useState('rising') // 단계 필터(클라이언트) — 기본 상승국면(1·6)
  const { data, loading, error, reload } = useFetch(() => fetchScreener(market, 30), [market])

  // catalog(6단계 라벨 SSOT — 백엔드가 내려줌) → stage → {name, phase} 조회 맵.
  // 프론트가 단계 이름을 복제하지 않도록 백엔드 카탈로그로 라벨/방향을 조회(useMemo 로 data 변경 시만 재구성).
  const stageMeta = useMemo(() => {
    const m = new Map()
    for (const s of data?.catalog?.stages || []) m.set(s.stage, s)
    return m
  }, [data])

  const candidates = data?.candidates || [] // 서버가 스캔한 전체 후보(단계 판정 포함)
  const active = STAGE_FILTERS.find((f) => f.key === filter) || STAGE_FILTERS[0] // 현재 필터 정의
  // 필터에 stages 목록이 있으면 그 단계만, null('전체 단계')이면 전부(클라이언트 필터 — 재조회 없음).
  const filtered = active.stages
    ? candidates.filter((c) => active.stages.includes(c.stage))
    : candidates
  const partial = data?.partial_failure || [] // 일봉 조회 실패로 단계가 빈 종목 목록(부분 실패 보존)

  return (
    <div className="screener">
      <div className="screener__controls">
        <div className="screener__markets" role="group" aria-label="시장 선택">
          {MARKETS.map((mk) => (
            <button
              key={mk.key}
              type="button"
              className={`screener__seg${market === mk.key ? ' is-active' : ''}`}
              aria-pressed={market === mk.key}
              onClick={() => setMarket(mk.key)}
            >
              {mk.label}
            </button>
          ))}
        </div>
        <div className="screener__stages" role="group" aria-label="대순환 단계 필터">
          {STAGE_FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              className={`screener__chip${filter === f.key ? ' is-active' : ''}`}
              aria-pressed={filter === f.key}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* 상태 분기: 최초 스캔 중 / 최초 조회 실패(재시도) / 결과(부분실패·개수·목록). 재조회 중엔
          이전 data 를 유지하므로 `&& !data` 로 최초 로딩·에러만 전면 표시(스왑 깜빡임 방지). */}
      {loading && !data ? (
        <div className="popup__state">후보 종목을 스캔하는 중… (시총상위 일봉 조회)</div>
      ) : error && !data ? (
        <div className="banner banner--warn">
          후보 조회에 실패했어요.{' '}
          <button type="button" className="banner__retry" onClick={reload}>
            다시 시도
          </button>
        </div>
      ) : (
        <>
          {partial.length > 0 && (
            <div className="screener__note">
              일부 종목은 일시 조회 실패로 단계가 비어 있어요({partial.length}종목).
            </div>
          )}
          <div className="screener__count">
            {filtered.length}종목 · {active.label}
          </div>
          {filtered.length === 0 ? (
            <div className="popup__state">
              해당 단계의 후보가 없어요. 다른 단계나 시장을 선택해 보세요.
            </div>
          ) : (
            <ul className="wl__list">
              {filtered.map((c) => (
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
function ScreenerRow({ c, meta, onOpenStock }) {
  const clickable = !!onOpenStock // onOpenStock 없으면 순수 표시(클릭 비활성·옵셔널)
  const openDetail = () => onOpenStock?.(c.ticker, c.name ?? c.ticker) // 상세 전환(종목명 전달)
  const hasStage = c.stage != null // 단계 판정 성공 여부(봉 부족·조회 실패 시 null)
  // 배지 라벨 — 백엔드 카탈로그(meta) 이름 우선, 없으면 서버가 준 stage_name 폴백.
  const stageLabel = hasStage ? `${c.stage}단계 · ${meta?.name ?? c.stage_name ?? ''}` : ''

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
          <span className="wl__meta">
            {c.ticker} · 시총 {marketCapJo(c.market_cap)}
          </span>
        </div>
        <div className="wl__row-price">
          <span className="wl__price">{num(c.price)}원</span>
          {/* 등락 칩은 ChangeChip SSOT(방향색 클래스+글리프+부호 규칙 공용). */}
          <ChangeChip value={c.change_rate} />
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
