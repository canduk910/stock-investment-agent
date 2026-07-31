import { useEffect, useRef, useState } from 'react'
import { readMermaidTheme } from '../lib/theme.js'

// mermaid 는 무겁다 → await import('mermaid') 동적 import 로 코드 스플리팅(별도 청크·지연 로드).
// initialize 는 최초 1회만(모듈 플래그로 가드). 팔레트는 theme.css 토큰(readMermaidTheme) SSOT.
let _initialized = false
async function loadMermaid() {
  const mermaid = (await import('mermaid')).default
  if (!_initialized) {
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'strict', // 원문 HTML/스크립트 주입 차단(기존 XSS 불변식 유지)
      flowchart: { htmlLabels: false },
      ...readMermaidTheme(),
    })
    _initialized = true
  }
  return mermaid
}

// 콜론 없는 고유 id — useId()의 ':' 는 mermaid 내부 querySelector 를 깨뜨리므로 쓰지 않는다.
// useRef 로 인스턴스당 한 번 고정한다.
let _idSeq = 0

// mermaid 다이어그램 렌더.
// - streaming(스트리밍 중·미완성 문법): mermaid 렌더 안 하고 <pre> 폴백만(동적 import 도 지연) → flicker/조기 로드 회피.
// - streaming=false(완료/히스토리 복원): mermaid.render 로 SVG 생성 후 그 SVG 만 주입(securityLevel:'strict').
//   bindFunctions 는 호출하지 않는다(이벤트 바인딩 불필요·안전).
// - 실패/로딩: 원본 텍스트 폴백(<pre>{chart}</pre>, React 자동 이스케이프).
export default function MermaidDiagram({ chart, streaming }) {
  const idRef = useRef(`mmd-${(_idSeq += 1)}`)
  const [svg, setSvg] = useState('')
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (streaming) {
      // 스트리밍 중: 렌더 보류. 이전 렌더 결과가 있으면 폴백으로 되돌린다.
      setSvg('')
      setFailed(false)
      return undefined
    }
    let cancelled = false
    const src = chart // 렌더 시작 시점의 코드 캡처(경합 방어 — stale 결과 무시)
    setFailed(false)
    ;(async () => {
      try {
        const mermaid = await loadMermaid()
        const out = await mermaid.render(idRef.current, src)
        if (!cancelled && src === chart) setSvg(out.svg)
      } catch {
        // 무효 문법 등: 폴백으로. 크래시하지 않는다.
        if (!cancelled && src === chart) {
          setSvg('')
          setFailed(true)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [chart, streaming])

  if (!streaming && !failed && svg) {
    // mermaid 가 strict 모드로 생성한 SVG 만 주입 — 원문 HTML 아님(XSS 불가).
    return (
      <div
        className="chat__mermaid"
        role="img"
        aria-label="다이어그램"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    )
  }
  // 스트리밍/로딩/실패: 원본 텍스트 폴백.
  return <pre className="chat__mermaid-fallback">{chart}</pre>
}
