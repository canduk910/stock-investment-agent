import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import DailySummary from './DailySummary.jsx'

// 금일의 요약 = **controlled/표시형** — 생성 상태·데이터는 상위(MacroDashboard)가 주입. 여기선 렌더만.
// 종합=여러 시황 리포트 인용·면책(에이전트 시장 판정 아님).

const DATA = {
  report_count: 5,
  summary: {
    시장전망분포: '중립 3·신중 2',
    종합요약: ['외국인 수급 개선', '실적 시즌 기대', '환율 변동성 유의'],
    면책고지: '이 종합은 여러 증권사 시황 리포트 내용이며 자문이 아니다.',
  },
}

describe('DailySummary(controlled) 렌더', () => {
  it('done + data → 10줄 종합·시장전망분포 칩·시황 N개 칩·면책', () => {
    render(<DailySummary state="done" data={DATA} />)
    expect(screen.getByText('금일의 요약')).toBeInTheDocument()
    expect(screen.getByText('외국인 수급 개선')).toBeInTheDocument()
    expect(screen.getByText('환율 변동성 유의')).toBeInTheDocument()
    expect(screen.getByText(/시장전망 · 중립 3·신중 2/)).toBeInTheDocument()
    expect(screen.getByText(/시황 5개 종합/)).toBeInTheDocument()
    expect(screen.getByText(/자문/)).toBeInTheDocument() // 면책
  })

  it('loading(자동 생성 중) → 스피너 안내, 생성 버튼 비활성', () => {
    render(<DailySummary state="loading" />)
    expect(screen.getByText(/최신 시황을 종합하는 중/)).toBeInTheDocument()
    expect(screen.getByText('생성 중…')).toBeDisabled()
  })

  it('error → 에러 메시지(role=alert)', () => {
    render(<DailySummary state="error" errMsg="금일의 요약을 생성하지 못했습니다." />)
    expect(screen.getByRole('alert')).toHaveTextContent('금일의 요약을 생성하지 못했습니다.')
  })

  it('idle → 생성 버튼 라벨 "금일의 요약 생성", 클릭 시 onGenerate', () => {
    const onGenerate = vi.fn()
    render(<DailySummary state="idle" onGenerate={onGenerate} />)
    const btn = screen.getByText('금일의 요약 생성')
    fireEvent.click(btn)
    expect(onGenerate).toHaveBeenCalled()
  })

  it('done → 버튼 라벨 "↻ 다시 생성"(재생성 경로)', () => {
    const onGenerate = vi.fn()
    render(<DailySummary state="done" data={DATA} onGenerate={onGenerate} />)
    fireEvent.click(screen.getByText('↻ 다시 생성'))
    expect(onGenerate).toHaveBeenCalled()
  })
})
