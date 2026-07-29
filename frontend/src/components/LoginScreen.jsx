import { useState } from 'react'
import { login, signup } from '../auth.js'
import DkMonogram from './DkMonogram.jsx'
import SegmentedControl from './SegmentedControl.jsx'

// 로그인/회원가입 화면 — 비로그인 시 App 이 전체 대신 이 화면을 렌더한다(인증 게이트).
// 성공하면 onAuthed(user)로 App 에 알린다. 비밀번호는 서버가 bcrypt 해시(프론트는 전송만).
// 색은 theme.css 토큰만. 로고(DkMonogram)는 톱바와 공유해 CI 일관(주황 마름모 포함).
//
// props: onAuthed(user) — 로그인/가입 성공 시 App 에 인증된 유저를 전달(App 이 게이트 해제).
// 하나의 폼으로 로그인·회원가입 두 모드(mode)를 토글 — 필드는 동일(이메일·비밀번호)하고 호출만 갈린다.

export default function LoginScreen({ onAuthed }) {
  const [mode, setMode] = useState('login') // 'login' | 'signup' — 탭으로 전환
  const [email, setEmail] = useState('') // 이메일 입력(제출 시 trim)
  const [password, setPassword] = useState('') // 비밀번호 입력(전송만·프론트 저장/해시 안 함)
  const [error, setError] = useState(null) // 실패 메시지(서버 사유 우선)
  const [busy, setBusy] = useState(false) // 요청 중 중복 제출·버튼 비활성

  const isSignup = mode === 'signup' // 현재 모드에 따라 호출 함수·라벨·placeholder 분기

  // 제출 — 모드에 따라 signup/login 호출. busy 가드로 더블 서브밋 방지. 성공 시 onAuthed 로 상위 통지.
  async function submit(e) {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const data = isSignup
        ? await signup(email.trim(), password)
        : await login(email.trim(), password)
      onAuthed?.(data.user) // App 이 이 user 로 인증 상태 세팅 → 게이트 해제
    } catch (err) {
      setError(err.message || '요청을 처리하지 못했습니다.')
    } finally {
      setBusy(false) // 성공/실패 무관 버튼 재활성(무한 대기 금지)
    }
  }

  // 탭 전환 — 이전 모드의 에러 메시지는 지운다(로그인 실패가 가입 탭에 남지 않게).
  function switchMode(next) {
    setMode(next)
    setError(null)
  }

  return (
    <div className="login">
      <div className="login__card">
        <div className="login__brand">
          <DkMonogram size={40} />
          <div>
            <h1 className="login__title">디케이 투자에이전트</h1>
            <p className="login__caption">로그인하고 나만의 관심종목·대화를 이어가세요</p>
          </div>
        </div>

        {/* 모드 탭 — SegmentedControl SSOT(aria-pressed 활성 표시). 클릭 시 필드 유지한 채 모드만 전환. */}
        <div className="login__tabs" role="tablist">
          <SegmentedControl
            options={[{ key: 'login', label: '로그인' }, { key: 'signup', label: '회원가입' }]}
            value={mode}
            onChange={switchMode}
            buttonClass="login__tab"
          />
        </div>

        <form className="login__form" onSubmit={submit} autoComplete="on">
          <label className="login__label">
            이메일
            <input
              className="login__input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
              required
            />
          </label>
          <label className="login__label">
            비밀번호
            {/* 회원가입 모드에선 최소 8자 강제(minLength)·autoComplete 도 new-password 로 힌트 */}
            <input
              className="login__input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={isSignup ? '8자 이상' : '비밀번호'}
              autoComplete={isSignup ? 'new-password' : 'current-password'}
              minLength={isSignup ? 8 : undefined}
              required
            />
          </label>

          {error ? (
            <p className="login__error" role="alert">
              {error}
            </p>
          ) : null}

          <button type="submit" className="login__submit" data-testid="login-submit" disabled={busy}>
            {busy ? '처리 중…' : isSignup ? '회원가입' : '로그인'}
          </button>
        </form>

        <p className="login__hint">
          {isSignup ? (
            <>이미 계정이 있으신가요?{' '}
              <button type="button" className="login__link" onClick={() => switchMode('login')}>
                로그인
              </button>
            </>
          ) : (
            <>처음이신가요?{' '}
              <button type="button" className="login__link" onClick={() => switchMode('signup')}>
                회원가입
              </button>
            </>
          )}
        </p>
      </div>
    </div>
  )
}
