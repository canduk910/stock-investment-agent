import { describe, it, expect } from 'vitest'
import { STAGES, stageChecklist } from './chatStages.js'

// 계약 근거(승인 계획 §프론트): SSE stage 이벤트(analyze|regime|outlook|generate|summarize)를
// 진행 체크리스트로 렌더한다 — 현재 stage 이전은 완료(done), 현재는 진행(active), 이후는 대기(pending).
// 이 상태 계산은 순수 로직이라 분리해 테스트한다(렌더는 ChatMessage 가 status→클래스 매핑만).
// outlook 은 시장 질문(macro_view)이 stale 시황을 동기 수집하는 동안만 등장(regime 다음·generate 앞).

describe('stageChecklist — 현재 stage → 단계별 status(done/active/pending)', () => {
  it('첫 단계(analyze) 진행 중 → analyze active, 나머지 pending', () => {
    const list = stageChecklist('analyze')
    expect(list.map((s) => s.status)).toEqual(['active', 'pending', 'pending', 'pending', 'pending'])
  })

  it('outlook 진행 중 → analyze·regime done, outlook active, 이후 pending', () => {
    const list = stageChecklist('outlook')
    expect(list.map((s) => [s.key, s.status])).toEqual([
      ['analyze', 'done'],
      ['regime', 'done'],
      ['outlook', 'active'],
      ['generate', 'pending'],
      ['summarize', 'pending'],
    ])
  })

  it('generate 진행 중 → 앞선 analyze·regime·outlook done, generate active, summarize pending', () => {
    const list = stageChecklist('generate')
    expect(list.map((s) => [s.key, s.status])).toEqual([
      ['analyze', 'done'],
      ['regime', 'done'],
      ['outlook', 'done'],
      ['generate', 'active'],
      ['summarize', 'pending'],
    ])
  })

  it('마지막 단계(summarize) 진행 중 → 앞 4개 done, summarize active', () => {
    const list = stageChecklist('summarize')
    expect(list.map((s) => s.status)).toEqual(['done', 'done', 'done', 'done', 'active'])
  })

  it('라벨은 STAGES 정의(한국어)를 그대로 노출', () => {
    const list = stageChecklist('regime')
    expect(list.find((s) => s.key === 'regime').label).toBe('시장 국면 조회')
    expect(list.find((s) => s.key === 'outlook').label).toBe('최신 시황 확인 중')
  })

  it('미지/결측 stage → 방어적으로 첫 단계 진행으로 간주(크래시·빈 리스트 금지)', () => {
    expect(stageChecklist(undefined).map((s) => s.status)).toEqual([
      'active',
      'pending',
      'pending',
      'pending',
      'pending',
    ])
    expect(stageChecklist('nope').length).toBe(STAGES.length)
  })
})

describe('STAGES — 진행 단계 계약 상수(백엔드 stage 이벤트와 단일 출처)', () => {
  it('정확히 5단계 analyze→regime→outlook→generate→summarize 순서', () => {
    expect(STAGES.map((s) => s.key)).toEqual([
      'analyze',
      'regime',
      'outlook',
      'generate',
      'summarize',
    ])
  })
})
