# 프로덕션 이미지(GCP Cloud Run) — 단일 서비스: FastAPI 가 API(/api/*) + 빌드된 React 정적파일 서빙.
# 로컬 개발용 Dockerfile(--reload·vite dev)과 별개. Cloud Run 은 $PORT(기본 8080)로 요청을 보낸다.
#
# 멀티스테이지: ① node 로 프론트 빌드(frontend/dist) → ② python 런타임에 백엔드 + dist 복사.

# ── 1) 프론트 빌드 ──────────────────────────────────────────────────────────
FROM node:20-slim AS frontend
WORKDIR /fe
# 잠금파일 기준 재현 설치(레이어 캐시).
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# vite build → /fe/dist (api.main 이 이 결과물을 정적 서빙).
RUN npm run build

# ── 2) 백엔드 런타임 ────────────────────────────────────────────────────────
FROM python:3.13-slim
# uv 정적 바이너리(별도 pip 부트스트랩 불필요).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
# scikit-learn 런타임 의존(OpenMP). slim 이미지엔 기본 미포함.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

# 의존성 레이어 캐시: 잠금파일만 먼저 복사해 설치(소스 변경 시 재설치 회피).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# 앱 소스 복사(.dockerignore 로 node_modules·.venv·.cache·.env·reports·_workspace 제외).
COPY . .
# 빌드된 프론트를 백엔드가 서빙하는 위치로 복사(소스의 stale dist 는 여기서 덮어씀).
COPY --from=frontend /fe/dist /app/frontend/dist

# Cloud Run 은 $PORT 로 헬스체크·트래픽을 보낸다(기본 8080). --reload 없음(프로덕션).
# exec form 은 env 확장을 못 하므로 sh -c 로 ${PORT} 확장.
CMD ["sh", "-c", "uv run --no-sync uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
