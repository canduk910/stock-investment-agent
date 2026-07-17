import { useCallback, useEffect, useState } from 'react'
import {
  fetchAdminUsers,
  updateAdminUser,
  resetAdminUserUsage,
  deleteAdminUser,
} from '../api.js'

// 관리자 패널(우측 세그먼트 '회원 관리' 탭 전용) — 유저 목록·이용 통계·질문 한도 제어·권한·삭제.
//   실데이터는 /api/admin/users 자체 조회(환각 차단). 모든 쓰기는 서버 API(get_admin_user 게이트).
//   조회·제어만(매매·비밀번호·KIS 원문 무관). 색은 theme.css 토큰만 — 확인 CTA=주황(--c-emph),
//   삭제는 파괴적이라 2단계 확인(빨강 경보 색은 손실·VIX 전용이라 여기선 오용 금지 → 뉴트럴 스타일).

// 관리자는 한도 무관(무제한) — 표시용.
function usageText(u) {
  const today = u.is_admin ? '무제한' : `${u.used_today}/${u.daily_limit}`
  return `오늘 ${today} · 누적 ${u.total_questions}회`
}

// 한 유저 카드 로우. 편집 상태(한도 초안·삭제 확인)는 로우 로컬. 쓰기 성공 시 부모가 목록을 갱신한다.
function UserRow({ user, isSelf, onPatched, onDeleted, onError }) {
  const [limitDraft, setLimitDraft] = useState(String(user.daily_limit))
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)

  // 서버 값이 바뀌면(다른 조작 후 재조회) 초안 동기화.
  useEffect(() => {
    setLimitDraft(String(user.daily_limit))
  }, [user.daily_limit])

  const limitChanged = limitDraft.trim() !== '' && Number(limitDraft) !== user.daily_limit
  const limitValid = /^\d+$/.test(limitDraft.trim())

  async function run(fn) {
    if (busy) return
    setBusy(true)
    try {
      await fn()
    } catch (e) {
      onError(e?.message || '작업에 실패했습니다.')
    } finally {
      setBusy(false)
    }
  }

  const toggleAdmin = () =>
    run(async () => onPatched(await updateAdminUser(user.id, { is_admin: !user.is_admin })))

  const saveLimit = () =>
    run(async () => {
      if (!limitValid) return onError('한도는 0 이상 정수여야 합니다.')
      onPatched(await updateAdminUser(user.id, { daily_limit: Number(limitDraft) }))
    })

  const resetUsage = () =>
    run(async () => onPatched(await resetAdminUserUsage(user.id)))

  const doDelete = () =>
    run(async () => {
      await deleteAdminUser(user.id)
      onDeleted(user.id)
    })

  return (
    <li className="admin__row">
      <div className="admin__row-main">
        <div className="admin__id">
          <span className="admin__email">{user.email}</span>
          {user.is_admin ? <span className="admin__badge">관리자</span> : null}
          {isSelf ? <span className="admin__badge admin__badge--self">나</span> : null}
        </div>
        <span className="admin__usage">{usageText(user)}</span>
      </div>

      <div className="admin__row-actions">
        <button
          type="button"
          className="admin__btn"
          onClick={toggleAdmin}
          disabled={busy || (isSelf && user.is_admin)}
          title={isSelf && user.is_admin ? '자기 자신의 관리자 권한은 해제할 수 없습니다.' : undefined}
        >
          {user.is_admin ? '일반 회원으로' : '관리자로'}
        </button>

        <span className="admin__limit">
          <label className="admin__limit-label">한도</label>
          <input
            className="admin__limit-input"
            type="number"
            min="0"
            value={limitDraft}
            onChange={(e) => setLimitDraft(e.target.value)}
            aria-label={`${user.email} 하루 질문 한도`}
            disabled={busy}
          />
          <button
            type="button"
            className="admin__btn admin__btn--emph"
            onClick={saveLimit}
            disabled={busy || !limitChanged || !limitValid}
          >
            저장
          </button>
        </span>

        <button type="button" className="admin__btn" onClick={resetUsage} disabled={busy}>
          사용량 리셋
        </button>

        {confirming ? (
          <span className="admin__confirm">
            <span className="admin__confirm-q">삭제할까요?</span>
            <button type="button" className="admin__btn admin__btn--emph" onClick={doDelete} disabled={busy}>
              확인
            </button>
            <button type="button" className="admin__btn" onClick={() => setConfirming(false)} disabled={busy}>
              취소
            </button>
          </span>
        ) : (
          <button
            type="button"
            className="admin__btn admin__btn--delete"
            onClick={() => setConfirming(true)}
            disabled={busy || isSelf}
            title={isSelf ? '자기 자신의 계정은 삭제할 수 없습니다.' : undefined}
          >
            삭제
          </button>
        )}
      </div>
    </li>
  )
}

export default function AdminPanel({ currentUserId }) {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setUsers(await fetchAdminUsers())
    } catch (e) {
      setError(e?.status === 403 ? '관리자 권한이 필요합니다.' : '회원 목록을 불러오지 못했습니다.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // 쓰기 성공 시 반환된 유저로 로컬 목록 갱신(재조회 없이 즉시 반영).
  const onPatched = useCallback((u) => {
    setActionError('')
    setUsers((list) => list.map((x) => (x.id === u.id ? u : x)))
  }, [])
  const onDeleted = useCallback((id) => {
    setActionError('')
    setUsers((list) => list.filter((x) => x.id !== id))
  }, [])

  if (loading) return <div className="popup__state">회원 목록 불러오는 중…</div>
  if (error) {
    return (
      <div className="popup__state">
        {error}
        <button type="button" className="refresh admin__retry" onClick={load}>
          다시 시도
        </button>
      </div>
    )
  }

  return (
    <div className="admin">
      <div className="admin__head">
        <span className="admin__count">회원 {users.length}명</span>
        <button type="button" className="refresh" onClick={load} disabled={loading}>
          새로고침
        </button>
      </div>

      {actionError ? (
        <div className="banner admin__action-error" role="alert">
          {actionError}
        </div>
      ) : null}

      <ul className="admin__list">
        {users.map((u) => (
          <UserRow
            key={u.id}
            user={u}
            isSelf={String(u.id) === String(currentUserId)}
            onPatched={onPatched}
            onDeleted={onDeleted}
            onError={setActionError}
          />
        ))}
      </ul>

      <p className="admin__note">
        질문 한도는 매일 자정(KST)에 자동 초기화됩니다. 관리자는 한도 없이 이용합니다.
      </p>
    </div>
  )
}
