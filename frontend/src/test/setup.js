// vitest 전역 셋업(IMP-17).
// - jest-dom 매처(toBeInTheDocument 등)를 vitest expect 에 확장.
// - 각 테스트 후 RTL DOM 정리(globals 미사용이라 자동 cleanup 이 안 걸리므로 명시 등록).
import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(cleanup)
