import { useState } from 'react'
import { login, signup } from '../auth.js'

// 로그인/회원가입 화면 — 비로그인 시 App 이 전체 대신 이 화면을 렌더한다(인증 게이트).
// 성공하면 onAuthed(user)로 App 에 알린다. 비밀번호는 서버가 bcrypt 해시(프론트는 전송만).
// 색은 theme.css 토큰만.

export default function LoginScreen({ onAuthed }) {
  const [mode, setMode] = useState('login') // 'login' | 'signup'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const isSignup = mode === 'signup'

  async function submit(e) {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const data = isSignup
        ? await signup(email.trim(), password)
        : await login(email.trim(), password)
      onAuthed?.(data.user)
    } catch (err) {
      setError(err.message || '요청을 처리하지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  function switchMode(next) {
    setMode(next)
    setError(null)
  }

  return (
    <div className="login">
      <div className="login__card">
        <div className="login__brand">
          <span className="login__logo">DK</span>
          <div>
            <h1 className="login__title">디케이 투자에이전트</h1>
            <p className="login__caption">로그인하고 나만의 관심종목·대화를 이어가세요</p>
          </div>
        </div>

        <div className="login__tabs" role="tablist">
          <button
            type="button"
            className="login__tab"
            aria-pressed={!isSignup}
            onClick={() => switchMode('login')}
          >
            로그인
          </button>
          <button
            type="button"
            className="login__tab"
            aria-pressed={isSignup}
            onClick={() => switchMode('signup')}
          >
            회원가입
          </button>
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
