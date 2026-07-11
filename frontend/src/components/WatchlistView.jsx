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
  addErrorMessage,
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
  // 편집/삭제 등 작업 결과 피드백 — 목록이 이미 떠 있어도(view 존재) 표시(IMP-10: 무음 실패 방지).
  const [actionError, setActionError] = useState(null)
  const [actionNote, setActionNote] = useState(null)
  // 정렬은 프론트 재배열이라 재조회 불필요. 초기값은 팝업 args 로 주입될 수 있다(enum 검증).
  const [sortBy, setSortBy] = useState(
    SORT_KEYS.includes(initialSortBy) ? initialSortBy : 'registered',
  )
  const onViewRef = useRef(onView)
  onViewRef.current = onView

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    // 새 조회(수동/60s refresh) 시작 시 지난 작업 피드백은 정리(스테일 방지).
    setActionError(null)
    setActionNote(null)
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
      await load() // 성공 → 재조회(actionError/Note 초기화) 후 확인 노트.
      setActionNote('관심종목을 제거했습니다.')
    } catch (e) {
      // 목록이 떠 있어도 보이는 dismissible 배너로 status 별 안내(무음 실패 금지).
      setActionError(addErrorMessage(e?.status))
    }
  }

  async function onSetTarget(ticker, current) {
    // 브라우저 prompt 금지 규칙 준수 위해 인라인 편집을 쓴다(아래 TargetCell). 이 핸들러는 확정값만 받는다.
    try {
      await updateWatchlistTarget(ticker, current)
      await load()
      setActionNote(current == null ? '목표가를 해제했습니다.' : '목표가를 저장했습니다.')
    } catch (e) {
      setActionError(addErrorMessage(e?.status))
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

      {/* ── 작업 피드백(편집/삭제) — 목록이 떠 있어도 표시(IMP-10: 무음 실패 방지) ── */}
      {actionError ? (
        <div className="banner banner--warn wl__action-msg" role="alert">
          {actionError}
          <button
            type="button"
            className="banner__retry"
            onClick={() => setActionError(null)}
            aria-label="알림 닫기"
          >
            ✕
          </button>
        </div>
      ) : null}
      {actionNote ? (
        <div className="wl__action-note" role="status">
          {actionNote}
        </div>
      ) : null}

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
        <div className="wl__list">
          {items.map((it) => (
            <WatchlistRow
              key={it.ticker}
              item={it}
              onRemove={() => onRemove(it.ticker)}
              onSetTarget={(v) => onSetTarget(it.ticker, v)}
            />
          ))}
        </div>
      )}

      <p className="wl__legend" role="note">
        상승 빨강 · 하락 파랑 — 한국 시장 관습 · 목표가 게이지는 매수 관점 근접도
      </p>
    </div>
  )
}

// 미니 스파크라인 — watchlist 응답의 spark(종가 시계열, 과거→현재)를 90×28 SVG 로 렌더.
//   선색 = 방향색(상승 --c-up 빨강 / 하락 --c-down 파랑 / 보합 --c-flat). spark 결측·2점 미만이면
//   렌더하지 않는다(백엔드 per-item graceful → 조용히 생략). 데이터는 백엔드가 조회(환각 차단).
function Sparkline({ points, dir }) {
  if (!Array.isArray(points)) return null
  const nums = points.filter((p) => Number.isFinite(Number(p))).map(Number)
  if (nums.length < 2) return null
  const w = 90
  const h = 28
  const pad = 3
  const min = Math.min(...nums)
  const max = Math.max(...nums)
  const range = max - min || 1
  const stepX = (w - pad * 2) / (nums.length - 1)
  const coords = nums.map((p, i) => [
    pad + i * stepX,
    pad + (h - pad * 2) * (1 - (p - min) / range),
  ])
  const d = coords
    .map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`)
    .join(' ')
  const [ex, ey] = coords[coords.length - 1]
  const stroke =
    dir === 'up' ? 'var(--c-up)' : dir === 'down' ? 'var(--c-down)' : 'var(--c-flat)'
  return (
    <svg className="wl__spark" width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
      <path
        d={d}
        fill="none"
        stroke={stroke}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={ex} cy={ey} r="2.2" fill={stroke} />
    </svg>
  )
}

// 목표가 근접 게이지 폭(%) — 매수 관점 근접도. |거리%|가 작을수록(가까울수록) 채움이 크다.
function gaugeWidth(distance) {
  if (!Number.isFinite(Number(distance))) return 6
  return Math.max(6, Math.min(100, 100 - Math.abs(Number(distance)) * 9))
}

function WatchlistRow({ item, onRemove, onSetTarget }) {
  const dir = changeDir(item.change_rate)
  const priceFailed = item.current_price == null
  const entry = entrySignalLabel(item.entry_signal)
  const targetBadge = TARGET_BADGE[item.target_status] ?? null

  return (
    <div className="wl__row">
      <div className="wl__row-top">
        <div className="wl__row-id">
          <span className="wl__name">{item.stock_name ?? item.ticker}</span>
          <span className="wl__meta">
            {item.ticker}
            {item.reason ? ` · ${item.reason}` : ''}
          </span>
        </div>
        <Sparkline points={item.spark} dir={dir} />
        <div className="wl__row-price">
          {priceFailed ? (
            <span className="wl__fail">조회 불가</span>
          ) : (
            <>
              <span className="wl__price">{num(item.current_price)}원</span>
              <span className={`wl__change ${dir ?? ''}`}>
                <span aria-hidden="true">
                  {dir === 'up' ? '▲' : dir === 'down' ? '▼' : '─'}
                </span>{' '}
                {signedPct(item.change_rate)}%
              </span>
            </>
          )}
        </div>
      </div>

      <div className="wl__row-bottom">
        <span className="wl__ratio">
          PER {item.per == null ? '—' : Number(item.per).toFixed(1)} · PBR{' '}
          {item.pbr == null ? '—' : Number(item.pbr).toFixed(2)}
        </span>
        <span className={`badge badge--${entry.tone}`}>{entry.text}</span>
        <TargetCell
          targetPrice={item.target_price}
          distance={item.distance_to_target}
          badge={targetBadge}
          onSetTarget={onSetTarget}
        />
        <button type="button" className="wl__remove" onClick={onRemove} aria-label="관심종목 제거">
          제거
        </button>
      </div>
    </div>
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
        <div className="wl__target-body">
          <div className="wl__target-head">
            <span className="wl__target-val">목표가 {num(targetPrice)}원</span>
            {Number.isFinite(distance) ? (
              <span className="wl__target-dist">({signedPct(distance, 1)}%)</span>
            ) : null}
            {badge ? <span className={`badge badge--${badge.tone}`}>{badge.text}</span> : null}
          </div>
          {/* 근접 게이지 — 도달/근접(주황) vs 여유(회색). 매수 관점 근접도(색만 아닌 폭으로도 표현). */}
          <div className="wl__gauge" aria-hidden="true">
            <span
              className={`wl__gauge-fill ${badge?.tone === 'emph' ? 'is-near' : ''}`}
              style={{ width: `${gaugeWidth(distance)}%` }}
            />
          </div>
        </div>
      ) : (
        <span className="wl__target-none">목표가 미설정</span>
      )}
      <button type="button" className="wl__target-edit-btn" onClick={() => setEditing(true)}>
        {targetPrice != null ? '변경' : '설정'}
      </button>
    </div>
  )
}
