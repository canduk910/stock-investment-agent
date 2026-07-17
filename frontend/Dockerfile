# 프론트(Vite 개발 서버) — 로컬 도커 기동. /api 호출은 백엔드 컨테이너로 프록시(VITE_PROXY_TARGET).
FROM node:20-slim
WORKDIR /app

# 의존성 레이어 캐시: 잠금파일 기준 재현 설치(npm ci).
# 설치 후 node_modules 를 바인드마운트(/app) '한 단계 위'(/node_modules)로 옮긴다 — 소스 볼륨이
# 이를 덮지 못하게. compose 의 빈 익명 볼륨이 호스트(mac) /app/node_modules 를 가리면, Node/Vite 는
# 상위로 올라가 /node_modules(이미지에 구운 리눅스 의존성)를 해석한다. 이 방식은 stale named volume 이
# 없어 이미지 재빌드 시 의존성이 항상 최신 — 컨테이너 내 재설치(npm install)가 영영 불필요하다.
COPY package.json package-lock.json ./
RUN npm ci && mv node_modules /node_modules

# .dockerignore 가 node_modules 를 제외하므로 /app 에는 소스만 복사된다(호스트 node_modules 미유입).
COPY . .

EXPOSE 5173
# --host 로 0.0.0.0 바인딩(컨테이너 외부 접근). 프록시 대상/폴링은 compose 환경변수로 주입.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
