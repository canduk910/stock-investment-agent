import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 개발 서버: /api 호출을 로컬 FastAPI(8000)로 프록시 → 브라우저 CORS 없이 동작.
// 프록시 대상은 VITE_PROXY_TARGET 로 재정의(도커: http://backend:8000 / 로컬 기본: 127.0.0.1:8000).
const proxyTarget = process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,          // 0.0.0.0 바인딩(컨테이너 외부 접근 허용). 로컬 실행에도 무해.
    port: 5173,
    proxy: {
      '/api': proxyTarget,
    },
    // 도커 볼륨에서 파일 변경 감지가 누락되면 폴링으로 전환(VITE_USE_POLLING=1).
    watch: process.env.VITE_USE_POLLING ? { usePolling: true } : undefined,
  },
})
