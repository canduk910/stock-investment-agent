// 프론트 인증 계층 — JWT 토큰 localStorage 보관 + authFetch(Bearer 주입) + 로그인/회원가입/me.
// 유저별 데이터 호출(관심종목·대화기록)은 authFetch 를 거쳐 서버가 토큰에서 user_id 를 얻는다.

const TOKEN_KEY = 'dk_auth_token'

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null // localStorage 불가 환경(테스트/프라이빗) graceful
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* 무시 */
  }
}

export function clearToken() {
  setToken(null)
}

// fetch 래퍼 — 토큰이 있으면 Authorization: Bearer 헤더를 주입한다. 401 은 호출부가 처리(로그아웃 유도).
export async function authFetch(url, opts = {}) {
  const token = getToken()
  const headers = { ...(opts.headers || {}) }
  if (token) headers.Authorization = `Bearer ${token}`
  return fetch(url, { ...opts, headers })
}

// POST /api/auth/signup {email,password} → {token, user}. 실패(409/422)는 err.status 실어 throw.
export async function signup(email, password) {
  const res = await fetch('/api/auth/signup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) {
    const err = new Error((await _detail(res)) || `API ${res.status}`)
    err.status = res.status
    throw err
  }
  const data = await res.json()
  setToken(data.token)
  return data
}

// POST /api/auth/login {email,password} → {token, user}. 불일치(401)는 err.status 실어 throw.
export async function login(email, password) {
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) {
    const err = new Error((await _detail(res)) || `API ${res.status}`)
    err.status = res.status
    throw err
  }
  const data = await res.json()
  setToken(data.token)
  return data
}

// GET /api/auth/me (Bearer) → {id, email}. 토큰 없음/무효는 null(비로그인).
export async function fetchMe() {
  if (!getToken()) return null
  try {
    const res = await authFetch('/api/auth/me')
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

export function logout() {
  clearToken()
}

async function _detail(res) {
  try {
    const body = await res.json()
    return body?.detail
  } catch {
    return null
  }
}
