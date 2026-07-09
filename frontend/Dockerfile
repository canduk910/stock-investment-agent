# 프론트(Vite 개발 서버) — 로컬 도커 기동. /api 호출은 백엔드 컨테이너로 프록시(VITE_PROXY_TARGET).
FROM node:20-slim
WORKDIR /app

# 의존성 레이어 캐시: 잠금파일 기준 재현 설치(npm ci).
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173
# --host 로 0.0.0.0 바인딩(컨테이너 외부 접근). 프록시 대상/폴링은 compose 환경변수로 주입.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
