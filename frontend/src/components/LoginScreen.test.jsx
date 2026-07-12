import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import LoginScreen from './LoginScreen.jsx'

vi.mock('../auth.js', () => ({ login: vi.fn(), signup: vi.fn() }))
import { login, signup } from '../auth.js'

beforeEach(() => {
  login.mockReset()
  signup.mockReset()
})

function fill(email, pw) {
  fireEvent.change(screen.getByLabelText('이메일'), { target: { value: email } })
  fireEvent.change(screen.getByLabelText('비밀번호'), { target: { value: pw } })
}

describe('LoginScreen', () => {
  it('로그인 제출 → login 호출 + onAuthed(user)', async () => {
    login.mockResolvedValue({ token: 't', user: { id: 1, email: 'a@b.com' } })
    const onAuthed = vi.fn()
    render(<LoginScreen onAuthed={onAuthed} />)
    fill('a@b.com', 'password123')
    fireEvent.click(screen.getByTestId('login-submit'))
    await waitFor(() => expect(login).toHaveBeenCalledWith('a@b.com', 'password123'))
    await waitFor(() => expect(onAuthed).toHaveBeenCalledWith({ id: 1, email: 'a@b.com' }))
  })

  it('회원가입 탭 전환 → signup 호출', async () => {
    signup.mockResolvedValue({ token: 't', user: { id: 2, email: 'new@x.com' } })
    const onAuthed = vi.fn()
    render(<LoginScreen onAuthed={onAuthed} />)
    // 회원가입 탭(aria-pressed=false 인 탭)으로 전환.
    fireEvent.click(screen.getByRole('button', { name: '회원가입', pressed: false }))
    fill('new@x.com', 'password123')
    fireEvent.click(screen.getByTestId('login-submit'))
    await waitFor(() => expect(signup).toHaveBeenCalledWith('new@x.com', 'password123'))
    await waitFor(() => expect(onAuthed).toHaveBeenCalled())
  })

  it('로그인 실패 → 에러 메시지 노출, onAuthed 미호출', async () => {
    login.mockRejectedValue(new Error('이메일 또는 비밀번호가 올바르지 않습니다.'))
    const onAuthed = vi.fn()
    render(<LoginScreen onAuthed={onAuthed} />)
    fill('a@b.com', 'wrongpass')
    fireEvent.click(screen.getByTestId('login-submit'))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/올바르지 않습니다/),
    )
    expect(onAuthed).not.toHaveBeenCalled()
  })
})
