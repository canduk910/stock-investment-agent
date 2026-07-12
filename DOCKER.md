# 로컬 도커 기동

백엔드(FastAPI)와 프론트(Vite)를 컨테이너 2개로 함께 띄운다. 로컬에 Python/uv/Node를 직접 설치하지 않아도 된다.

## 사전 준비
- Docker Desktop(또는 Docker Engine + Compose v2).
- 프로젝트 루트에 `.env` — `.env.example`을 복사해 키를 채운다(KIS/FRED/DART/OPENAI). 시크릿은 이미지에 굽지 않고 런타임 주입된다.

## 기동
```bash
docker compose up --build      # 최초 또는 의존성 변경 시
docker compose up              # 이후 재기동
```
- 프론트: http://localhost:5173
- 백엔드 헬스: http://localhost:8000/api/health
- 프론트의 `/api` 호출은 컨테이너 네트워크에서 백엔드(`http://backend:8000`)로 프록시된다(CORS 불필요).

## 중지 / 정리
```bash
docker compose down            # 컨테이너 중지·제거(볼륨 보존)
docker compose down -v         # node_modules·.venv 캐시 볼륨까지 제거(클린 재빌드)
```

## 핫리로드
- 백엔드: 소스가 볼륨 마운트되고 `uvicorn --reload`(폴링) — `*.py` 저장 시 자동 재시작.
- 프론트: Vite HMR(폴링, `VITE_USE_POLLING=1`) — 컴포넌트 저장 시 즉시 반영.

## `.env` 변경 반영 (주의 — restart로는 안 됨)
`.env`(env_file)는 **컨테이너 생성 시점에만 주입**된다. 소스처럼 볼륨 마운트가 아니라서 핫리로드 대상이 아니다.
- `docker compose restart`는 프로세스만 재시작 → **env_file을 다시 읽지 않는다**(옛 값 유지).
- `.env`를 고쳤으면 컨테이너를 **재생성**해야 한다:
  ```bash
  docker compose up -d --force-recreate backend   # .env 재주입(backend만 env_file 사용)
  ```
- 프론트는 `.env`가 아니라 compose 인라인 `environment`(VITE_PROXY_TARGET 등)를 쓰므로 `.env` 변경과 무관하다.
- 확인(값 미노출): `docker compose exec -T backend sh -c 'test -n "$KIS_ACNT_NO" && echo set || echo empty'`.

## 자주 쓰는 명령
```bash
docker compose exec backend uv run pytest         # 백엔드 테스트
docker compose exec frontend npm test             # 프론트 테스트(vitest)
docker compose logs -f backend                    # 로그 추적
docker compose exec backend uv run python chat/intent_train.py   # 인텐트 모델 재학습
```

## 설계 메모
- 백엔드는 `build-system` 없는 run-from-source 앱이라 `uv sync --no-install-project`로 의존성만 설치하고 `PYTHONPATH=/app`으로 실행한다.
- 호스트(mac)에서 빌드된 `.venv`/`node_modules`가 컨테이너(Linux)를 덮지 않도록 named 볼륨(`backend-venv`, `frontend-node-modules`)으로 격리한다.
- scikit-learn 런타임용 `libgomp1`을 백엔드 이미지에 설치한다.
- `.env`는 `.dockerignore`로 이미지 빌드에서 제외 → 시크릿이 이미지 레이어에 남지 않는다.

## 유저베이스(인증·DB) — 도커 주의
- **DB env**: `.env`에 `DATABASE_URL`(미설정 시 로컬 SQLite `sqlite:///.cache/app.db`; 프로덕션 GCP Cloud SQL Postgres `postgresql+psycopg://…`)·`JWT_SECRET`(≥32B, 프로덕션 필수). 컨테이너는 `env_file`로 주입.
- **★deps 추가 후 컨테이너 sync**: 백엔드는 `backend-venv` 볼륨(이미지 빌드 시점 설치)을 쓴다. 호스트에서 `uv add`로 새 파이썬 패키지를 추가하면 컨테이너 venv엔 없어 `--reload`가 ImportError로 죽는다 → **`docker compose exec backend uv sync`**(또는 `docker compose up --build`)로 컨테이너에 설치. (예: sqlalchemy·bcrypt·pyjwt 추가 시 겪음.)
- SQLite 파일 DB는 `.cache/app.db`(볼륨 마운트 `./:/app`로 호스트와 공유·gitignore).
