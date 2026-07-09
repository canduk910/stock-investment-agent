# 백엔드(FastAPI) — 로컬 도커 기동.
# uv 로 의존성 설치 후 소스에서 실행(run-from-source, pythonpath=/app; 이 앱은 build-system 없는
# 애플리케이션이라 패키지로 설치하지 않는다 → uv sync --no-install-project).
FROM python:3.13-slim

# uv 정적 바이너리 복사 — 별도 pip 부트스트랩 불필요.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# scikit-learn 런타임 의존(OpenMP). slim 이미지엔 기본 미포함이라 명시 설치.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    WATCHFILES_FORCE_POLLING=true

# 의존성 레이어 캐시: 잠금파일만 먼저 복사해 설치(소스 변경 시 재설치 회피).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# 앱 소스 복사(compose 볼륨이 런타임에 덮어써 핫리로드; 이미지 단독 실행도 되게 포함).
COPY . .

EXPOSE 8000
# 0.0.0.0 바인딩(컨테이너 외부 접근) + --reload(소스 볼륨 변경 감지, WATCHFILES_FORCE_POLLING).
CMD ["uv", "run", "--no-sync", "uvicorn", "api.main:app", \
     "--host", "0.0.0.0", "--port", "8000", "--reload"]
