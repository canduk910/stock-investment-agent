import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import FetchProgress, { applyProgressEvent } from './FetchProgress.jsx'

describe('applyProgressEvent 리듀서', () => {
  it('stage → 스테이지 갱신', () => {
    expect(applyProgressEvent(null, { type: 'stage', stage: 'list' }).stage).toBe('list')
  })

  it('found → 리스트를 pending 으로 렌더 준비', () => {
    const p = applyProgressEvent(null, {
      type: 'found',
      reports: [{ id: '1', broker: '한화', title: 't1' }, { id: '2', broker: '미래', title: 't2' }],
    })
    expect(p.stage).toBe('process')
    expect(p.total).toBe(2)
    expect(p.reports.every((r) => r.status === 'pending')).toBe(true)
  })

  it('progress → 해당 id 만 상태 갱신 + done 카운트', () => {
    let p = applyProgressEvent(null, { type: 'found', reports: [{ id: '1', broker: 'a', title: 'x' }, { id: '2', broker: 'b', title: 'y' }] })
    p = applyProgressEvent(p, { type: 'progress', id: '2', result: 'new', done: 1, total: 2 })
    expect(p.done).toBe(1)
    expect(p.reports.find((r) => r.id === '2').status).toBe('new')
    expect(p.reports.find((r) => r.id === '1').status).toBe('pending') // 미완료 = 처리 중
  })
})

describe('FetchProgress 렌더', () => {
  it('progress 없으면 아무것도 안 그림', () => {
    const { container } = render(<FetchProgress progress={null} />)
    expect(container.firstChild).toBeNull()
  })

  it('목록 조회 단계 표시', () => {
    render(<FetchProgress progress={{ stage: 'list', reports: [], done: 0, total: 0 }} />)
    expect(screen.getByText(/리포트 목록을 가져오는 중/)).toBeInTheDocument()
  })

  it('처리 단계: i/N + 각 리포트 항목(증권사·제목·상태)', () => {
    render(
      <FetchProgress
        progress={{
          stage: 'process',
          done: 1,
          total: 2,
          reports: [
            { id: '1', broker: '한화투자증권', title: '투자포인트', status: 'new' },
            { id: '2', broker: '미래에셋', title: '기대감', status: 'pending' },
          ],
        }}
      />,
    )
    expect(screen.getByText(/리포트 처리 중 · 1\/2/)).toBeInTheDocument()
    expect(screen.getByText(/한화투자증권/)).toBeInTheDocument()
    expect(screen.getByText('새 요약')).toBeInTheDocument()
    expect(screen.getByText('처리 중…')).toBeInTheDocument() // pending = 처리 중
  })
})
