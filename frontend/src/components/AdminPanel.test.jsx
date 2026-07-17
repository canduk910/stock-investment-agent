import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import AdminPanel from './AdminPanel.jsx'

// 관리자 패널 — 경계(api.js)만 mock. 목록·통계 렌더·한도 저장·권한 토글·삭제 2단계·자기 자신 가드 검증.

vi.mock('../api.js', () => ({
  fetchAdminUsers: vi.fn(),
  updateAdminUser: vi.fn(),
  resetAdminUserUsage: vi.fn(),
  deleteAdminUser: vi.fn(),
}))
import {
  fetchAdminUsers,
  updateAdminUser,
  resetAdminUserUsage,
  deleteAdminUser,
} from '../api.js'

const USERS = [
  { id: 1, email: 'admin@a.com', is_admin: true, daily_limit: 20, used_today: 5, remaining: null, total_questions: 40 },
  { id: 2, email: 'member@a.com', is_admin: false, daily_limit: 20, used_today: 20, remaining: 0, total_questions: 99 },
]

beforeEach(() => {
  fetchAdminUsers.mockReset().mockResolvedValue(USERS)
  updateAdminUser.mockReset()
  resetAdminUserUsage.mockReset()
  deleteAdminUser.mockReset()
})

describe('AdminPanel', () => {
  it('회원 목록·이용 통계를 렌더한다(관리자 무제한 표기)', async () => {
    render(<AdminPanel currentUserId={1} />)
    await waitFor(() => expect(screen.getByText('admin@a.com')).toBeInTheDocument())
    expect(screen.getByText('member@a.com')).toBeInTheDocument()
    expect(screen.getByText(/오늘 무제한 · 누적 40회/)).toBeInTheDocument()
    expect(screen.getByText(/오늘 20\/20 · 누적 99회/)).toBeInTheDocument()
    expect(screen.getByText('회원 2명')).toBeInTheDocument()
  })

  it('한도 편집 → updateAdminUser(id, {daily_limit}) 호출', async () => {
    updateAdminUser.mockResolvedValue({ ...USERS[1], daily_limit: 5 })
    render(<AdminPanel currentUserId={1} />)
    await waitFor(() => expect(screen.getByText('member@a.com')).toBeInTheDocument())
    const input = screen.getByLabelText('member@a.com 하루 질문 한도')
    fireEvent.change(input, { target: { value: '5' } })
    const saveBtns = screen.getAllByRole('button', { name: '저장' })
    fireEvent.click(saveBtns[1]) // member 행
    await waitFor(() => expect(updateAdminUser).toHaveBeenCalledWith(2, { daily_limit: 5 }))
  })

  it('권한 토글 → updateAdminUser(id, {is_admin}) 호출', async () => {
    updateAdminUser.mockResolvedValue({ ...USERS[1], is_admin: true })
    render(<AdminPanel currentUserId={1} />)
    await waitFor(() => expect(screen.getByText('member@a.com')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: '관리자로' }))
    await waitFor(() => expect(updateAdminUser).toHaveBeenCalledWith(2, { is_admin: true }))
  })

  it('자기 자신은 관리자 해제·삭제 버튼이 비활성(락아웃 방지)', async () => {
    render(<AdminPanel currentUserId={1} />)
    await waitFor(() => expect(screen.getByText('admin@a.com')).toBeInTheDocument())
    // admin@a.com(자기 자신) 행: '일반 회원으로'(관리자 해제) 비활성
    expect(screen.getByRole('button', { name: '일반 회원으로' })).toBeDisabled()
    // 자기 자신 행 삭제 버튼 비활성 — 삭제 버튼 2개 중 admin 행(첫 번째)
    const deleteBtns = screen.getAllByRole('button', { name: '삭제' })
    expect(deleteBtns[0]).toBeDisabled()
    expect(deleteBtns[1]).not.toBeDisabled() // member 행은 삭제 가능
  })

  it('삭제는 2단계 확인 후 deleteAdminUser 호출 + 목록에서 제거', async () => {
    deleteAdminUser.mockResolvedValue({ ok: true, deleted: 2 })
    render(<AdminPanel currentUserId={1} />)
    await waitFor(() => expect(screen.getByText('member@a.com')).toBeInTheDocument())
    const deleteBtns = screen.getAllByRole('button', { name: '삭제' })
    fireEvent.click(deleteBtns[1]) // member 삭제 시작
    expect(deleteAdminUser).not.toHaveBeenCalled() // 아직 확인 전
    fireEvent.click(screen.getByRole('button', { name: '확인' }))
    await waitFor(() => expect(deleteAdminUser).toHaveBeenCalledWith(2))
    await waitFor(() => expect(screen.queryByText('member@a.com')).not.toBeInTheDocument())
  })

  it('403(권한 없음)은 안내 + 다시 시도', async () => {
    const err = new Error('403')
    err.status = 403
    fetchAdminUsers.mockRejectedValueOnce(err)
    render(<AdminPanel currentUserId={9} />)
    await waitFor(() => expect(screen.getByText(/관리자 권한이 필요합니다/)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: '다시 시도' })).toBeInTheDocument()
  })
})
