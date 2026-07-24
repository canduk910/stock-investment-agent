import { useMemo, useState } from 'react'
import { fetchScreener } from '../api.js'
import { useFetch } from '../lib/useFetch.js'
import { stageGlyph } from '../lib/grandCycle.js'
import { num, signedNum, changeDir } from '../lib/format.js'

// 대순환(고지로) 단계 기반 후보 종목 스크리너 — 시총상위 유니버스를 대순환 단계로 스캔.
//   판정(단계)은 백엔드 엔진(코드)이 확정, 여기선 표시·필터만. 실데이터는 프론트가 직접 조회(환각 차단).
//   색: 단계 배지=주황 강조(--c-emph)+방향 글리프, 등락=방향색(--c-up/down). 경보색·hex 금지.

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
  const [market, setMarket] = useState('all')
  const [filter, setFilter] = useState('rising') // 기본 상승국면
  const { data, loading, error, reload } = useFetch(() => fetchScreener(market, 30), [market])

  // catalog(6단계 라벨 SSOT — 백엔드가 내려줌) → stage → {name, phase} 조회 맵.
  const stageMeta = useMemo(() => {
    const m = new Map()
    for (const s of data?.catalog?.stages || []) m.set(s.stage, s)
    return m
  }, [data])

  const candidates = data?.candidates || []
  const active = STAGE_FILTERS.find((f) => f.key === filter) || STAGE_FILTERS[0]
  const filtered = active.stages
    ? candidates.filter((c) => active.stages.includes(c.stage))
    : candidates
  const partial = data?.partial_failure || []

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

function ScreenerRow({ c, meta, onOpenStock }) {
  const dir = changeDir(c.change_rate)
  const clickable = !!onOpenStock
  const openDetail = () => onOpenStock?.(c.ticker, c.name ?? c.ticker)
  const hasStage = c.stage != null
  const stageLabel = hasStage ? `${c.stage}단계 · ${meta?.name ?? c.stage_name ?? ''}` : ''

  return (
    <li className="wl__row">
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
          <span className={`wl__change ${dir ?? ''}`}>
            <span aria-hidden="true">{dir === 'up' ? '▲' : dir === 'down' ? '▼' : '─'}</span>{' '}
            {signedNum(c.change_rate)}%
          </span>
        </div>
      </div>
      <div className="wl__row-bottom">
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
