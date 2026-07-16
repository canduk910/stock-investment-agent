import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ChatMessage from './ChatMessage.jsx'

// 봇(LLM) 응답은 마크다운 렌더, 사용자 입력은 평문. react-markdown 기본은 원문 HTML 미렌더(XSS 불가).

describe('ChatMessage 마크다운', () => {
  it('봇 응답의 마크다운을 요소로 렌더(제목·굵게·기울임·목록·코드·링크)', () => {
    const md =
      '## 제목\n\n**굵게** 그리고 *기울임*\n\n- 항목1\n- 항목2\n\n`인라인코드`\n\n[네이버](https://naver.com)'
    const { container } = render(<ChatMessage role="bot" text={md} popups={[]} />)
    expect(container.querySelector('.chat__md h2')).toBeTruthy()
    expect(container.querySelector('.chat__md strong')).toBeTruthy()
    expect(container.querySelector('.chat__md em')).toBeTruthy()
    expect(container.querySelectorAll('.chat__md li').length).toBe(2)
    expect(container.querySelector('.chat__md code')).toBeTruthy()
    // 마크다운 기호가 문자로 남지 않고 요소로 렌더됨.
    expect(screen.getByText('굵게').tagName).toBe('STRONG')
    // 링크는 새 탭 + 보안 rel.
    const link = container.querySelector('.chat__md a')
    expect(link.getAttribute('href')).toBe('https://naver.com')
    expect(link.getAttribute('target')).toBe('_blank')
    expect(link.getAttribute('rel')).toContain('noopener')
  })

  it('GFM 표도 렌더', () => {
    const table = '| 지표 | 값 |\n| --- | --- |\n| VIX | 20 |'
    const { container } = render(<ChatMessage role="bot" text={table} popups={[]} />)
    expect(container.querySelector('.chat__md table')).toBeTruthy()
    expect(container.querySelectorAll('.chat__md td').length).toBeGreaterThan(0)
  })

  it('사용자 메시지는 평문(마크다운 미적용)', () => {
    const { container } = render(<ChatMessage role="user" text="**굵게 아님**" popups={[]} />)
    expect(container.querySelector('.chat__md')).toBeFalsy()
    expect(container.querySelector('strong')).toBeFalsy()
    expect(screen.getByText('**굵게 아님**')).toBeInTheDocument() // 친 문자 그대로
  })

  it('원문 HTML(이미지/스크립트)은 렌더하지 않는다(XSS 불가)', () => {
    const { container } = render(
      <ChatMessage role="bot" text={'<img src=x onerror="alert(1)"> 안녕'} popups={[]} />,
    )
    expect(container.querySelector('img')).toBeFalsy() // 태그가 아니라 문자로 이스케이프
    expect(container.querySelector('script')).toBeFalsy()
  })

  it('스트리밍 중 봇 응답에 커서 병기', () => {
    const { container } = render(<ChatMessage role="bot" text="응답 중" popups={[]} streaming />)
    expect(container.querySelector('.chat__cursor')).toBeTruthy()
  })
})
