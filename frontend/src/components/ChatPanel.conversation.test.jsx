import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import ChatPanel from './ChatPanel.jsx'

// 대화기록 연계 — 대화 전환 시 저장 메시지 로드(role 매핑) + 새 대화/선택 콜백.
vi.mock('../api.js', () => ({
  postChat: vi.fn(),
  postChatStream: vi.fn(),
  fetchConversationMessages: vi.fn(),
}))
import { fetchConversationMessages } from '../api.js'

beforeEach(() => {
  fetchConversationMessages.mockReset()
  fetchConversationMessages.mockResolvedValue({
    conversation: { id: 1, title: '대화' },
    messages: [
      { role: 'user', content: '삼성전자 어때?' },
      { role: 'assistant', content: '설명입니다.' },
    ],
  })
})

const baseProps = {
  sessionId: '1',
  conversationId: 1,
  conversations: [
    { id: 1, title: '대화 A' },
    { id: 2, title: '대화 B' },
  ],
  onNewConversation: vi.fn(),
  onSelectConversation: vi.fn(),
  onRenameConversation: vi.fn(),
}

describe('ChatPanel 대화기록', () => {
  it('대화 진입 시 저장 메시지를 로드해 말풍선 복원(assistant→bot)', async () => {
    render(<ChatPanel {...baseProps} />)
    await waitFor(() => expect(fetchConversationMessages).toHaveBeenCalledWith(1))
    await waitFor(() => expect(screen.getByText('삼성전자 어때?')).toBeInTheDocument())
    expect(screen.getByText('설명입니다.')).toBeInTheDocument()
  })

  it('"새 대화" 버튼 → onNewConversation 호출', async () => {
    const onNew = vi.fn()
    render(<ChatPanel {...baseProps} onNewConversation={onNew} />)
    await waitFor(() => screen.getByText('+ 새 대화'))
    fireEvent.click(screen.getByText('+ 새 대화'))
    expect(onNew).toHaveBeenCalled()
  })

  it('대화 선택(드롭다운) → onSelectConversation(id)', async () => {
    const onSelect = vi.fn()
    render(<ChatPanel {...baseProps} onSelectConversation={onSelect} />)
    await waitFor(() => screen.getByLabelText('대화 선택'))
    fireEvent.change(screen.getByLabelText('대화 선택'), { target: { value: '2' } })
    expect(onSelect).toHaveBeenCalledWith(2)
  })

  it('✎ → 인라인 편집(현재 제목) → 수정·저장 시 onRenameConversation(id, title)', async () => {
    const onRename = vi.fn()
    render(<ChatPanel {...baseProps} onRenameConversation={onRename} />)
    await waitFor(() => screen.getByLabelText('대화 이름 수정'))
    fireEvent.click(screen.getByLabelText('대화 이름 수정'))
    const input = screen.getByLabelText('대화 이름')
    expect(input.value).toBe('대화 A') // 현재 대화(id 1) 제목으로 진입
    fireEvent.change(input, { target: { value: '삼성전자 분석' } })
    fireEvent.click(screen.getByLabelText('이름 저장'))
    expect(onRename).toHaveBeenCalledWith(1, '삼성전자 분석')
  })

  it('편집 중 빈 제목이면 저장 비활성', async () => {
    render(<ChatPanel {...baseProps} />)
    await waitFor(() => screen.getByLabelText('대화 이름 수정'))
    fireEvent.click(screen.getByLabelText('대화 이름 수정'))
    fireEvent.change(screen.getByLabelText('대화 이름'), { target: { value: '   ' } })
    expect(screen.getByLabelText('이름 저장')).toBeDisabled()
  })

  it('✕(취소) → 편집 종료, 스위처 복귀·rename 미호출', async () => {
    const onRename = vi.fn()
    render(<ChatPanel {...baseProps} onRenameConversation={onRename} />)
    await waitFor(() => screen.getByLabelText('대화 이름 수정'))
    fireEvent.click(screen.getByLabelText('대화 이름 수정'))
    fireEvent.click(screen.getByLabelText('편집 취소'))
    await waitFor(() => expect(screen.getByLabelText('대화 선택')).toBeInTheDocument())
    expect(onRename).not.toHaveBeenCalled()
  })

  it('🗑 → 2단계 확인(삭제?) → onDeleteConversation(id) 호출', async () => {
    const onDelete = vi.fn()
    render(<ChatPanel {...baseProps} onDeleteConversation={onDelete} />)
    await waitFor(() => screen.getByLabelText('대화 삭제'))
    fireEvent.click(screen.getByLabelText('대화 삭제'))
    expect(onDelete).not.toHaveBeenCalled() // 1클릭은 확인 노출만
    fireEvent.click(screen.getByLabelText('대화 삭제 확인'))
    expect(onDelete).toHaveBeenCalledWith(1)
  })

  it('삭제 확인 취소(✕) → onDeleteConversation 미호출·버튼 복귀', async () => {
    const onDelete = vi.fn()
    render(<ChatPanel {...baseProps} onDeleteConversation={onDelete} />)
    await waitFor(() => screen.getByLabelText('대화 삭제'))
    fireEvent.click(screen.getByLabelText('대화 삭제'))
    fireEvent.click(screen.getByLabelText('삭제 취소'))
    await waitFor(() => expect(screen.getByLabelText('대화 삭제')).toBeInTheDocument())
    expect(onDelete).not.toHaveBeenCalled()
  })

  it('onDeleteConversation 미전달이면 삭제 버튼 없음(옵셔널·하위호환)', async () => {
    render(<ChatPanel {...baseProps} />)
    await waitFor(() => screen.getByLabelText('대화 이름 수정'))
    expect(screen.queryByLabelText('대화 삭제')).toBeNull()
  })
})
