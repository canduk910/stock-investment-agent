import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 개발 서버: /api 호출을 로컬 FastAPI(8000)로 프록시 → 브라우저 CORS 없이 동작.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
