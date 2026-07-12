import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import KisSettingsPanel from './KisSettingsPanel.jsx'

// 유저별 KIS 키 설정 — 경계(api.js)만 mock. 상태 렌더·검증에러·저장/삭제 호출·시크릿 미노출 검증.

vi.mock('../api.js', () => ({
  fetchKisCredentialsStatus: vi.fn(),
  setKisCredentials: vi.fn(),
  deleteKisCredentials: vi.fn(),
}))
import { fetchKisCredentialsStatus, setKisCredentials, deleteKisCredentials } from '../api.js'

beforeEach(() => {
  fetchKisCredentialsStatus.mockReset()
  setKisCredentials.mockReset()
  deleteKisCredentials.mockReset()
})

describe('KisSettingsPanel', () => {
  it('공유 fallback 상태면 "공유 데모 키" 안내 + 등록 폼', async () => {
    fetchKisCredentialsStatus.mockResolvedValue({ registered: false, source: 'shared' })
    render(<KisSettingsPanel />)
    await waitFor(() => expect(screen.getByText(/공유 데모 키로 조회 중/)).toBeInTheDocument())
    expect(screen.getByLabelText('앱키')).toBeInTheDocument()
    expect(screen.getByLabelText('앱시크릿')).toHaveAttribute('type', 'password') // 시크릿 가림
  })

  it('등록됨(source=user)이면 마스킹 상태 + 삭제 버튼', async () => {
    fetchKisCredentialsStatus.mockResolvedValue({
      registered: true, source: 'user', app_key_masked: 'PS••••12', account_masked: '12••••78', env: 'real',
    })
    render(<KisSettingsPanel />)
    await waitFor(() => expect(screen.getByText(/내 KIS 키 등록됨/)).toBeInTheDocument())
    expect(screen.getByText(/PS••••12/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /내 키 삭제/ })).toBeInTheDocument()
  })

  it('폼 제출 → setKisCredentials(body) 호출·성공 안내, 원문 시크릿은 화면에 텍스트로 안 남음', async () => {
    fetchKisCredentialsStatus
      .mockResolvedValueOnce({ registered: false, source: 'none' })
      .mockResolvedValue({ registered: true, source: 'user', app_key_masked: 'PS••••99', account_masked: '', env: 'real' })
    setKisCredentials.mockResolvedValue({
      ok: true, status: { registered: true, source: 'user', app_key_masked: 'PS••••99', account_masked: '', env: 'real' },
    })
    render(<KisSettingsPanel />)
    await waitFor(() => screen.getByLabelText('앱키'))
    fireEvent.change(screen.getByLabelText('앱키'), { target: { value: 'PSmykey99' } })
    fireEvent.change(screen.getByLabelText('앱시크릿'), { target: { value: 'SECRETplain' } })
    fireEvent.click(screen.getByRole('button', { name: /검증 후 저장/ }))
    await waitFor(() =>
      expect(setKisCredentials).toHaveBeenCalledWith(
        expect.objectContaining({ app_key: 'PSmykey99', app_secret: 'SECRETplain', env: 'real' }),
      ),
    )
    await waitFor(() => expect(screen.getByText(/검증하고 암호화 저장/)).toBeInTheDocument())
    // 시크릿 원문이 화면 텍스트로 노출되지 않음(입력값은 password input value 라 textContent 아님).
    expect(document.body.textContent).not.toContain('SECRETplain')
  })

  it('검증 실패(400)면 에러 배너 표시', async () => {
    fetchKisCredentialsStatus.mockResolvedValue({ registered: false, source: 'none' })
    setKisCredentials.mockRejectedValue(new Error('KIS 키 검증 실패 — app_key/app_secret/env(real·demo)를 확인하세요.'))
    render(<KisSettingsPanel />)
    await waitFor(() => screen.getByLabelText('앱키'))
    fireEvent.change(screen.getByLabelText('앱키'), { target: { value: 'BAD' } })
    fireEvent.change(screen.getByLabelText('앱시크릿'), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: /검증 후 저장/ }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/KIS 키 검증 실패/))
  })

  it('삭제 버튼 → deleteKisCredentials 호출·공유 전환 안내', async () => {
    fetchKisCredentialsStatus.mockResolvedValue({
      registered: true, source: 'user', app_key_masked: 'PS••••12', account_masked: '', env: 'real',
    })
    deleteKisCredentials.mockResolvedValue({ ok: true, status: { registered: false, source: 'shared' } })
    render(<KisSettingsPanel />)
    await waitFor(() => screen.getByRole('button', { name: /내 키 삭제/ }))
    fireEvent.click(screen.getByRole('button', { name: /내 키 삭제/ }))
    await waitFor(() => expect(deleteKisCredentials).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByText(/내 KIS 키를 삭제했습니다/)).toBeInTheDocument())
  })
})
