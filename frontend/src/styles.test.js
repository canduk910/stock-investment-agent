// Phase 0 — 전역 스타일 계약 테스트 (키프레임 5종 + .skeleton + Pretendard).
//
// styles.css 원본 텍스트를 파싱해 리디자인이 요구하는 애니메이션/유틸/폰트 스택이
// 정의됐는지 고정한다(TOKENS_AND_CSS_SPEC.md §2·§3). jsdom 은 CSS 를 적용하지 않으므로
// 텍스트 존재 검증이 회귀를 잡는 실용적 경계다.
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { describe, it, expect } from 'vitest'

const __dirname = dirname(fileURLToPath(import.meta.url))
const stylesCss = readFileSync(join(__dirname, 'styles.css'), 'utf8')

describe('styles.css — 키프레임 5종 신규(§3)', () => {
  // marker-ring(HTML box-shadow 펄스)은 통합 사분면에서 SVG-safe `rtraj-pulse`(transform scale)로 대체됨.
  const frames = ['rtraj-pulse', 'rise-in', 'shimmer', 'flash-up', 'flash-down']
  for (const name of frames) {
    it(`@keyframes ${name} 정의`, () => {
      expect(stylesCss).toMatch(new RegExp(`@keyframes\\s+${name}\\b`))
    })
  }
  it('기존 키프레임 stage-pulse·blink 유지', () => {
    expect(stylesCss).toMatch(/@keyframes\s+stage-pulse\b/)
    expect(stylesCss).toMatch(/@keyframes\s+blink\b/)
  })
})

describe('styles.css — 스켈레톤 유틸(§3)', () => {
  it('.skeleton 클래스 존재 + shimmer 애니메이션 사용', () => {
    expect(stylesCss).toMatch(/\.skeleton\b/)
    expect(stylesCss).toMatch(/animation:\s*shimmer/)
  })
})

describe('styles.css — 타이포(§2)', () => {
  it('body font-family 에 Pretendard 스택', () => {
    expect(stylesCss).toMatch(/Pretendard/)
  })
  it('숫자 tabular-nums(font-variant-numeric)', () => {
    expect(stylesCss).toMatch(/font-variant-numeric:\s*tabular-nums/)
  })
})

describe('styles.css — 색 규칙 인라인 주석 개정(색 반전)', () => {
  it('종목 등락률 방향색이 --c-chart-up/down 중복 예외를 제거하고 --c-up/--c-down 로 통합', () => {
    // .report__change.up/down 이 캔들 전용 토큰(--c-chart-*)을 참조하지 않아야 한다.
    const block = stylesCss.slice(
      stylesCss.indexOf('.report__change.up'),
      stylesCss.indexOf('.report__change.up') + 220,
    )
    expect(block).not.toContain('--c-chart-up')
    expect(block).not.toContain('--c-chart-down')
    expect(block).toContain('--c-up')
    expect(block).toContain('--c-down')
  })
})
