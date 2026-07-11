// Phase 0 — 디자인 토큰 SSOT 계약 테스트 (리디자인 컨셉 A "Refined Pro").
//
// theme.css 는 팔레트의 단일 출처(SSOT)다. 색 반전(상승=빨강/하락=파랑)과 신규 셸 토큰이
// 스펙(TOKENS_AND_CSS_SPEC.md §1)대로 정의됐는지 원본 텍스트를 파싱해 고정한다.
// jsdom 은 실제 CSS 를 파싱/적용하지 않으므로(computed color 미검증), 토큰 "정의값"을
// 계약으로 검증하는 것이 색 반전 회귀를 잡는 가장 확실한 방법이다.
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { describe, it, expect } from 'vitest'

const __dirname = dirname(fileURLToPath(import.meta.url))
const themeCss = readFileSync(join(__dirname, 'theme.css'), 'utf8')

// ":root { ... }" 안에서 "--name: value;" 를 뽑아 { name: value } 맵으로.
function parseTokens(css) {
  const map = {}
  const re = /(--[\w-]+)\s*:\s*([^;]+);/g
  let m
  while ((m = re.exec(css)) !== null) {
    map[m[1]] = m[2].trim()
  }
  return map
}
const tokens = parseTokens(themeCss)

describe('theme.css — 색 반전(§1-1)', () => {
  it('--c-up = #e5322d (상승 = 빨강, 한국 관습)', () => {
    expect(tokens['--c-up']).toBe('#e5322d')
  })
  it('--c-down = #2563eb (하락 = 파랑)', () => {
    expect(tokens['--c-down']).toBe('#2563eb')
  })
  it('--c-up 은 더 이상 파랑 토큰(var(--c-blue))을 참조하지 않는다', () => {
    expect(tokens['--c-up']).not.toContain('--c-blue')
  })
  it('--c-down 은 더 이상 회색 토큰을 참조하지 않는다', () => {
    expect(tokens['--c-down']).not.toContain('--c-text-secondary')
  })
})

describe('theme.css — 셸/형태 값 교체(§1-1)', () => {
  it('--c-bg = #f5f7fb', () => {
    expect(tokens['--c-bg']).toBe('#f5f7fb')
  })
  it('--c-border = #e2e8f2 (더 옅게)', () => {
    expect(tokens['--c-border']).toBe('#e2e8f2')
  })
  it('--radius = 14px', () => {
    expect(tokens['--radius']).toBe('14px')
  })
  it('--shadow-card 는 2단 그림자(16,35,61 알파)', () => {
    expect(tokens['--shadow-card']).toContain('rgba(16, 35, 61, 0.05)')
    expect(tokens['--shadow-card']).toContain('0 8px 24px')
  })
})

describe('theme.css — 신규 토큰(§1-2) 전부 정의', () => {
  const required = {
    // 방향 소프트
    '--c-up-soft': 'rgba(229, 50, 45, 0.08)',
    '--c-down-soft': '#e8f0fe',
    '--c-flat': '#8a94a8',
    '--c-flat-soft': '#f0f3f9',
    '--c-up-onnavy': '#ff7a75',
    // 브랜드/셸
    '--c-brand': '#1d4ed8',
    '--c-navy-deep': '#101b30',
    '--c-emph-onnavy': '#f0913c',
    // 표면 보조
    '--c-surface-3': '#f8fafd',
    '--c-border-soft': '#e9edf5',
    '--c-hairline': '#f0f3f9',
    // 강조 보더
    '--c-emph-border': '#f0c9a2',
    // 텍스트 보조
    '--c-text-faint': '#a3adc0',
    // 형태
    '--radius-lg': '16px',
    '--radius-xl': '18px',
    '--radius-pill': '999px',
  }
  for (const [name, value] of Object.entries(required)) {
    it(`${name} = ${value}`, () => {
      expect(tokens[name]).toBe(value)
    })
  }
})

describe('theme.css — 유지 토큰(§1-3) 변경 금지', () => {
  it('--c-chart-up = #e5322d (캔들 예외 유지)', () => {
    expect(tokens['--c-chart-up']).toBe('#e5322d')
  })
  it('--c-chart-down = #2563eb (캔들 예외 유지)', () => {
    expect(tokens['--c-chart-down']).toBe('#2563eb')
  })
  it('--c-emph 계열(강조 주황) 유지', () => {
    expect(tokens['--c-emph']).toBe('#e0670f')
    expect(tokens['--c-emph-strong']).toBe('#b8500a')
    expect(tokens['--c-emph-soft']).toBe('#fbe8d6')
  })
  it('--c-danger 계열(위험 빨강) 유지', () => {
    expect(tokens['--c-danger']).toBe('#d92d20')
    expect(tokens['--c-danger-strong']).toBe('#b42318')
  })
})
