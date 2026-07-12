import { useEffect, useState } from 'react'
import { deleteKisCredentials, fetchKisCredentialsStatus, setKisCredentials } from '../api.js'

// 유저별 KIS API 키 설정 — 등록/상태/삭제. 시크릿은 서버로만 전송되고 화면·응답엔 원문이 없다
// (상태는 마스킹만). 저장은 서버가 실제 KIS 토큰 발급으로 검증 후 암호화 저장한다.
// 색은 theme.css 토큰만(저장 CTA=주황 강조 --c-emph, 에러=파랑 배너 --c-blue). LoginScreen 폼 패턴 재사용.

const HELP =
  'KIS Open API 홈페이지에서 발급한 앱키/시크릿을 입력하세요. 키는 암호화되어 저장되며 ' +
  '화면·로그·응답에 원문이 노출되지 않습니다. 미등록 시 공유 데모 키로 조회됩니다.'

export default function KisSettingsPanel() {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState({ app_key: '', app_secret: '', account_no: '', env: 'real' })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function loadStatus() {
    setLoading(true)
    setError('')
    try {
      setStatus(await fetchKisCredentialsStatus())
    } catch (e) {
      setError(`상태를 불러오지 못했습니다(${e.message}).`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadStatus()
  }, [])

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const canSave = form.app_key.trim() && form.app_secret.trim() && !saving

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const res = await setKisCredentials(form)
      setStatus(res.status)
      setNotice('KIS 키를 검증하고 암호화 저장했습니다.')
      setForm({ app_key: '', app_secret: '', account_no: '', env: form.env })
    } catch (e) {
      setError(e.message) // "KIS 키 검증 실패 …"
    } finally {
      setSaving(false)
    }
  }

  async function remove() {
    setError('')
    setNotice('')
    try {
      const res = await deleteKisCredentials()
      setStatus(res.status)
      setNotice('내 KIS 키를 삭제했습니다. 이후 공유 데모 키로 조회됩니다.')
    } catch (e) {
      setError(`삭제에 실패했습니다(${e.message}).`)
    }
  }

  return (
    <section className="kis-settings" aria-label="KIS API 키 설정">
      {loading ? (
        <div className="popup__state">설정 불러오는 중…</div>
      ) : status?.source === 'user' ? (
        <div className="kis-settings__status" role="status">
          <span className="chip chip--navy">✓ 내 KIS 키 등록됨</span>
          <span className="kis-settings__meta">
            앱키 {status.app_key_masked} · 계좌 {status.account_masked || '미설정'} · {status.env}
          </span>
          <button type="button" className="refresh kis-settings__delete" onClick={remove}>
            내 키 삭제(공유 키로 전환)
          </button>
        </div>
      ) : (
        <div className="kis-settings__status" role="status">
          <span className="kis-settings__meta">
            {status?.source === 'shared'
              ? '현재 공유 데모 키로 조회 중입니다. 내 계좌·시세를 쓰려면 아래에 KIS 키를 등록하세요.'
              : '등록된 KIS 키가 없습니다. 아래에 등록하세요.'}
          </span>
        </div>
      )}

      <form className="kis-settings__form" onSubmit={save} autoComplete="off">
        <label className="login__label">
          앱키 (App Key)
          <input
            className="login__input"
            value={form.app_key}
            onChange={set('app_key')}
            placeholder="PS..."
            aria-label="앱키"
          />
        </label>
        <label className="login__label">
          앱시크릿 (App Secret)
          <input
            className="login__input"
            type="password"
            value={form.app_secret}
            onChange={set('app_secret')}
            aria-label="앱시크릿"
          />
        </label>
        <label className="login__label">
          계좌번호 (선택 · 잔고 조회용)
          <input
            className="login__input"
            value={form.account_no}
            onChange={set('account_no')}
            placeholder="12345678-01"
            aria-label="계좌번호"
          />
        </label>
        <label className="login__label">
          환경
          <select className="login__input" value={form.env} onChange={set('env')} aria-label="환경">
            <option value="real">실전 (real)</option>
            <option value="demo">모의 (demo)</option>
          </select>
        </label>

        {error ? (
          <p className="banner banner--warn kis-settings__error" role="alert">
            {error}
          </p>
        ) : null}
        {notice ? (
          <p className="kis-settings__notice" role="status">
            {notice}
          </p>
        ) : null}

        <button type="submit" className="kis-settings__save" disabled={!canSave}>
          {saving ? '검증·저장 중…' : '검증 후 저장'}
        </button>
      </form>

      <p className="kis-settings__help" role="note">
        {HELP}
      </p>
    </section>
  )
}
