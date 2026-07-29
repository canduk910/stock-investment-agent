import { useCallback, useEffect, useState } from 'react'
import LoadState from './LoadState.jsx'
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
//
// props: currentUserId — 로그인한 관리자 자신의 id. 자기 자신 대상 조작(관리자 해제·삭제)은
//   락아웃 방지를 위해 UI 에서 비활성(서버도 400 으로 짝을 이룬다).
// 데이터 흐름: 로컬 목록(users)을 단일 소유하고, 각 행의 쓰기가 성공하면 서버가 돌려준 유저 객체로
//   해당 행만 즉시 교체(재조회 없이) — onPatched/onDeleted 콜백.

// 카드에 표시할 이용 통계 문자열. 관리자는 질문 한도가 없어 '무제한'으로 표기(순수 표시 함수).
function usageText(u) {
  const today = u.is_admin ? '무제한' : `${u.used_today}/${u.daily_limit}`
  return `오늘 ${today} · 누적 ${u.total_questions}회`
}

// 한 유저 카드 로우. 편집 상태(한도 초안·삭제 확인)는 로우 로컬. 쓰기 성공 시 부모가 목록을 갱신한다.
function UserRow({ user, isSelf, onPatched, onDeleted, onError }) {
  const [limitDraft, setLimitDraft] = useState(String(user.daily_limit)) // 한도 입력 초안(문자열·검증 후 숫자화)
  const [confirming, setConfirming] = useState(false) // 삭제 2단계 확인 진입 여부
  const [busy, setBusy] = useState(false) // 이 행의 어떤 쓰기든 진행 중이면 모든 버튼 비활성

  // 서버 값이 바뀌면(다른 조작 후 재조회) 초안 동기화 — 외부 변경이 편집 초안을 덮어써야 정합.
  useEffect(() => {
    setLimitDraft(String(user.daily_limit))
  }, [user.daily_limit])

  // 저장 활성 조건: 값이 비지 않고 서버 값과 다를 때만(변경 없으면 저장 버튼 비활성).
  const limitChanged = limitDraft.trim() !== '' && Number(limitDraft) !== user.daily_limit
  const limitValid = /^\d+$/.test(limitDraft.trim()) // 0 이상 정수만 허용(음수·소수·문자 차단)

  // 공용 실행 래퍼 — busy 가드로 중복 실행 방지, 실패는 onError 로 상위에 표면화, 항상 busy 해제.
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

  // 관리자 권한 토글 — 반환 유저를 onPatched 로 올려 로컬 목록 즉시 갱신.
  const toggleAdmin = () =>
    run(async () => onPatched(await updateAdminUser(user.id, { is_admin: !user.is_admin })))

  // 한도 저장 — 클라이언트에서 한 번 더 정수 검증(서버 검증의 사전 방어) 후 PATCH.
  const saveLimit = () =>
    run(async () => {
      if (!limitValid) return onError('한도는 0 이상 정수여야 합니다.')
      onPatched(await updateAdminUser(user.id, { daily_limit: Number(limitDraft) }))
    })

  // 오늘 사용량 리셋(누적은 유지) — 서버가 갱신된 유저 반환.
  const resetUsage = () =>
    run(async () => onPatched(await resetAdminUserUsage(user.id)))

  // 삭제 — 유저와 스코프 데이터(관심종목·대화·KIS 키)까지 서버가 정리. 성공 시 목록에서 제거.
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
        {/* 관리자 토글 — 자기 자신이 관리자면 해제 불가(락아웃 방지). title 로 사유 안내 */}
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

        {/* 삭제 = 2단계 확인. confirming=true 면 확인/취소 노출, 아니면 '삭제' 버튼(자기 자신은 비활성) */}
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
  const [users, setUsers] = useState([]) // 회원 목록(단일 소유·행 조작이 부분 갱신)
  const [loading, setLoading] = useState(true) // 최초/새로고침 조회 중
  const [error, setError] = useState('') // 목록 조회 실패(전체 상태·재시도 버튼)
  const [actionError, setActionError] = useState('') // 개별 행 조작 실패(상단 배너·목록은 유지)

  // 회원 목록 조회 — 403 은 관리자 권한 부재로 구분 안내(비관리자 접근).
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

  // 마운트·load 참조 변경 시 조회.
  useEffect(() => {
    load()
  }, [load])

  // 쓰기 성공 시 반환된 유저로 로컬 목록 갱신(재조회 없이 즉시 반영) — 이전 조작 에러도 함께 해제.
  const onPatched = useCallback((u) => {
    setActionError('')
    setUsers((list) => list.map((x) => (x.id === u.id ? u : x)))
  }, [])
  const onDeleted = useCallback((id) => {
    setActionError('')
    setUsers((list) => list.filter((x) => x.id !== id))
  }, [])

  // 로딩/에러 박스는 LoadState SSOT — 라벨('다시 시도')·클래스(admin__retry)만 자리 주입.
  if (loading) return <LoadState loading loadingText="회원 목록 불러오는 중…" />
  if (error) {
    return (
      <LoadState
        error
        errorContent={error}
        onRetry={load}
        retryLabel="다시 시도"
        retryClassName="refresh admin__retry"
      />
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
            /* id 타입이 섞일 수 있어(number/string) 문자열 비교로 자기 자신 판정 */
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
