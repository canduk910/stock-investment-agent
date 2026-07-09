import { useCallback, useEffect, useRef, useState } from 'react'
import {
  fetchWatchlist,
  removeWatchlist,
  updateWatchlistTarget,
} from '../api.js'
import {
  SORT_KEYS,
  SORT_LABELS,
  sortItems,
  entrySignalLabel,
} from '../lib/watchlistLogic.js'

// 워치리스트 본문 — 팝업(PopupWatchlist)과 독립 패널(App)이 공유하는 단일 컴포넌트.
// 원칙: 시세·진입신호 등 실데이터는 여기가 API 로 직접 조회한다(환각 차단). LLM 응답은 "무엇을 띄울지"만.
//   - 정렬은 재조회 없이 프론트 순수 로직(watchlistLogic.sortItems)으로 재배열한다.
//   - 부분 실패(partial_failure)는 섹션별 조용한 안내로 표시하고 나머지는 정상 렌더(전체 에러 화면 금지).
//   - 색은 theme.css 토큰만. 상승=파랑/하락=회색, 진입 검토가능·목표가 도달/근접=강조 주황(빨강 금지).
//
// props(모두 옵션):
//   initialSortBy  : 팝업이 show_watchlist args.sort_by 를 주입(기본 'registered').
//   refreshKey     : 값이 바뀌면 재조회(App 의 60s interval 이 증가시킨다). 팝업은 미전달(마운트 1회).
//   onView         : 조회 성공 시 최신 view 를 부모에 통지(App 의 목표가 전이 알림 근거). 팝업은 미전달.

const num = (v, digits = 0) => {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return '—'
  return Number(v).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}
const signedPct = (v, digits = 2) => {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return '—'
  const n = Number(v)
  return `${n > 0 ? '+' : ''}${n.toFixed(digits)}`
}
const changeDir = (v) => {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return null
  return Number(v) > 0 ? 'up' : Number(v) < 0 ? 'down' : 'flat'
}

// 목표가 상태 배지 문구·톤. reached/near = 강조 주황(매수 관점 신호), far/none = 회색. 위험(빨강) 아님.
const TARGET_BADGE = {
  reached: { text: '목표가 도달', tone: 'emph' },
  near: { text: '목표가 근접', tone: 'emph' },
  far: { text: '목표가까지 여유', tone: 'muted' },
  none: null,
}

// partial_failure(문자열 리스트/객체 둘 다 방어) 에 값이 있는지.
function inPartialFailure(partialFailure, key) {
  if (!Array.isArray(partialFailure)) return false
  return partialFailure.some((e) => (typeof e === 'string' ? e === key : e?.section === key))
}

export default function WatchlistView({ initialSortBy, refreshKey, onView }) {
  const [view, setView] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  // 정렬은 프론트 재배열이라 재조회 불필요. 초기값은 팝업 args 로 주입될 수 있다(enum 검증).
  const [sortBy, setSortBy] = useState(
    SORT_KEYS.includes(initialSortBy) ? initialSortBy : 'registered',
  )
  const onViewRef = useRef(onView)
  onViewRef.current = onView

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // sort_by 는 서버 에코용으로만 전달(실제 정렬은 프론트). 시세 부분실패는 200 이라 throw 안 함.
      const v = await fetchWatchlist(sortBy)
      setView(v)
      onViewRef.current?.(v) // App 의 목표가 전이 알림 근거로 통지.
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
    // sortBy 재조회 회피: 정렬은 프론트에서 하므로 load 는 refreshKey/마운트에만 반응.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 마운트 + refreshKey 변화 시 재조회(App 의 60s interval 이 refreshKey 를 올린다).
  useEffect(() => {
    load()
  }, [load, refreshKey])

  async function onRemove(ticker) {
    try {
      await removeWatchlist(ticker)
      await load()
    } catch (e) {
      setError(e.message)
    }
  }

  async function onSetTarget(ticker, current) {
    // 브라우저 prompt 금지 규칙 준수 위해 인라인 편집을 쓴다(아래 TargetCell). 이 핸들러는 확정값만 받는다.
    try {
      await updateWatchlistTarget(ticker, current)
      await load()
    } catch (e) {
      setError(e.message)
    }
  }

  if (loading && !view) {
    return <div className="wl__state">관심종목을 불러오는 중…</div>
  }
  if (error && !view) {
    return (
      <div className="banner banner--warn wl__error" role="status">
        관심종목을 가져오지 못했습니다({error}).
        <button type="button" className="banner__retry" onClick={load}>
          ↻ 재시도
        </button>
      </div>
    )
  }
  if (!view) return null

  const items = sortItems(view.items ?? [], sortBy)
  const regime = view.regime ?? null
  const regimeFailed = inPartialFailure(view.partial_failure, 'regime')
  const failedTickers = (view.partial_failure ?? []).filter((e) => typeof e === 'string' && e !== 'regime')

  return (
    <div className="wl">
      {/* ── 국면 배너: 현재 국면 + 신규진입 억제 여부(과열 등). 국면명은 주황(강조). ── */}
      {regime && !regimeFailed ? (
        <div className={`wl__regime ${regime.entry_blocked ? 'is-blocked' : ''}`} role="note">
          <span className="wl__regime-label">현재 국면</span>
          <span className="wl__regime-name">{regime.regime ?? '—'}</span>
          {regime.entry_blocked ? (
            <span className="wl__regime-flag">신규 진입 억제 국면 · 진입 신호 미표시</span>
          ) : (
            <span className="wl__regime-note">
              신규 진입 검토 가능 국면 (권장 비중 한도 {num(regime.single_cap)}%)
            </span>
          )}
        </div>
      ) : (
        <div className="wl__regime wl__regime--fail" role="note">
          국면 정보 일시 조회 불가 · 진입 신호는 표시하지 않습니다(시세는 정상 표시).
        </div>
      )}

      {/* ── 정렬 드롭다운(재조회 없이 프론트 재배열) ── */}
      <div className="wl__toolbar">
        <label className="wl__sort">
          정렬
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} aria-label="정렬 기준">
            {SORT_KEYS.map((k) => (
              <option key={k} value={k}>
                {SORT_LABELS[k]}
              </option>
            ))}
          </select>
        </label>
        {loading ? <span className="wl__refreshing">갱신 중…</span> : null}
      </div>

      {failedTickers.length > 0 ? (
        <div className="banner banner--warn wl__partial" role="status">
          일부 종목 시세 일시 조회 불가({failedTickers.join(', ')}) · 나머지는 정상 표시
        </div>
      ) : null}

      {items.length === 0 ? (
        <div className="wl__empty">
          관심종목이 없습니다. 종목 리포트에서 “관심종목 추가”로 담아보세요.
        </div>
      ) : (
        <div className="wl__table-wrap">
          <table className="wl__table">
            <thead>
              <tr>
                <th scope="col">종목</th>
                <th scope="col" className="wl__num">현재가</th>
                <th scope="col" className="wl__num">등락률</th>
                <th scope="col" className="wl__num">PER / PBR</th>
                <th scope="col">진입 신호</th>
                <th scope="col">목표가</th>
                <th scope="col" aria-label="관리" />
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <WatchlistRow
                  key={it.ticker}
                  item={it}
                  onRemove={() => onRemove(it.ticker)}
                  onSetTarget={(v) => onSetTarget(it.ticker, v)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function WatchlistRow({ item, onRemove, onSetTarget }) {
  const dir = changeDir(item.change_rate)
  const priceFailed = item.current_price == null
  const entry = entrySignalLabel(item.entry_signal)
  const targetBadge = TARGET_BADGE[item.target_status] ?? null

  return (
    <tr>
      <th scope="row" className="wl__name-cell">
        <span className="wl__name">{item.stock_name ?? item.ticker}</span>
        <span className="wl__ticker">{item.ticker}</span>
        {item.reason ? <span className="wl__reason">{item.reason}</span> : null}
      </th>
      <td className="wl__num">
        {priceFailed ? <span className="wl__fail">조회 불가</span> : `${num(item.current_price)}원`}
      </td>
      <td className="wl__num">
        {priceFailed ? (
          '—'
        ) : (
          <span className={`wl__change ${dir ?? ''}`}>
            <span aria-hidden="true">
              {dir === 'up' ? '▲' : dir === 'down' ? '▼' : '─'}
            </span>{' '}
            {signedPct(item.change_rate)}%
          </span>
        )}
      </td>
      <td className="wl__num wl__ratio">
        {item.per == null ? '—' : `${Number(item.per).toFixed(1)}`}
        {' / '}
        {item.pbr == null ? '—' : `${Number(item.pbr).toFixed(2)}`}
      </td>
      <td>
        <span className={`badge badge--${entry.tone}`}>{entry.text}</span>
      </td>
      <td>
        <TargetCell
          targetPrice={item.target_price}
          distance={item.distance_to_target}
          badge={targetBadge}
          onSetTarget={onSetTarget}
        />
      </td>
      <td className="wl__actions">
        <button type="button" className="wl__remove" onClick={onRemove} aria-label="관심종목 제거">
          제거
        </button>
      </td>
    </tr>
  )
}

// 목표가 셀 — 표시 + 인라인 편집(브라우저 prompt 금지 규칙 준수). 비어있으면 "설정" 버튼.
function TargetCell({ targetPrice, distance, badge, onSetTarget }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(targetPrice != null ? String(targetPrice) : '')

  function commit(e) {
    e.preventDefault()
    const raw = draft.trim()
    const val = raw === '' ? null : Number(raw)
    if (raw !== '' && (!Number.isFinite(val) || val < 0)) return // 불량 입력 무시(음수·비수치)
    onSetTarget(val)
    setEditing(false)
  }

  if (editing) {
    return (
      <form className="wl__target-edit" onSubmit={commit}>
        <input
          className="wl__target-input"
          type="number"
          min="0"
          step="1"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          aria-label="목표가 입력(원)"
          autoFocus
        />
        <button type="submit" className="wl__target-save">저장</button>
        <button
          type="button"
          className="wl__target-cancel"
          onClick={() => {
            setDraft(targetPrice != null ? String(targetPrice) : '')
            setEditing(false)
          }}
        >
          취소
        </button>
      </form>
    )
  }

  return (
    <div className="wl__target">
      {targetPrice != null ? (
        <>
          <span className="wl__target-val">{num(targetPrice)}원</span>
          {badge ? <span className={`badge badge--${badge.tone}`}>{badge.text}</span> : null}
          {Number.isFinite(distance) ? (
            <span className="wl__target-dist">({signedPct(distance, 1)}%)</span>
          ) : null}
        </>
      ) : (
        <span className="wl__target-none">미설정</span>
      )}
      <button type="button" className="wl__target-edit-btn" onClick={() => setEditing(true)}>
        {targetPrice != null ? '변경' : '설정'}
      </button>
    </div>
  )
}
