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
})
