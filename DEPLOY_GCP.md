# GCP 배포 (Cloud Run + Cloud SQL) — 런북

프로덕션 배포 아키텍처와 재현 절차. 로컬 개발(도커 컴포즈)은 `DOCKER.md` 참고 — **무변경**.

## 아키텍처 (단일 서비스)

**단일 Cloud Run 서비스**가 FastAPI API(`/api/*`)와 **빌드된 React 정적파일**을 같은 오리진에서 서빙한다.
프론트가 전부 상대경로 `/api` 호출이라 **동일 오리진 → CORS·프론트 코드 변경 0, SSE 그대로 동작**.
서비스 1개라 비용·구성 최소.

```
브라우저 ──HTTPS──▶ Cloud Run: dk-invest-agent (asia-northeast3)
                      │  FastAPI(uvicorn) : /api/* + / (React dist)
                      │  Secret Manager 주입(env)
                      └─unix socket─▶ Cloud SQL: dk-invest-db (POSTGRES_15, db-f1-micro)
                                         DB: appdb
```

- **빌드**: 루트 `Dockerfile`(프로덕션·멀티스테이지) — ① node 로 `frontend/` vite build → ② python 런타임에
  백엔드 + `frontend/dist` 복사, `uvicorn --port $PORT`(reload 없음). 로컬 개발용은 `Dockerfile.dev`(compose 가 참조).
- **정적 서빙**: `api/main.py` 말미가 `frontend/dist` 를 서빙 + 404 예외 핸들러로 SPA 폴백(비-API GET 만).
  `/api` 405/404·JSON 에러는 불변. dist 없으면(로컬·테스트) 블록 skip → 무영향.
- **DB**: `infra/db.py` 가 `DATABASE_URL` 로 스왑(로컬 SQLite ↔ Cloud SQL Postgres). 드라이버 `psycopg[binary]`.
  연결은 unix socket `/cloudsql/<CONNECTION_NAME>`. `init_db()`(startup)가 `create_all`.

## 리소스 (이미 생성됨)

| 항목 | 값 |
|------|-----|
| 프로젝트 | `dk-invest-agent-2607122107` (번호 `816686454504`) |
| 리전 | `asia-northeast3` (서울) |
| Cloud SQL | `dk-invest-db` (POSTGRES_15, db-f1-micro, HDD 10GB, zonal, no-backup) |
| 연결 이름 | `dk-invest-agent-2607122107:asia-northeast3:dk-invest-db` |
| 데이터베이스 | `appdb` (유저: `postgres`) |
| Cloud Run | `dk-invest-agent` |
| 런타임 SA | `816686454504-compute@developer.gserviceaccount.com` (secretAccessor) |

## 시크릿 (Secret Manager, `:latest`)

| 시크릿 | 출처 | 주입 env |
|--------|------|----------|
| `OPENAI_API_KEY` `KIS_APP_KEY` `KIS_APP_SECRET` `KIS_ACCOUNT_NO` `KIS_ACNT_NO` `FRED_API_KEY` | 로컬 `.env`(사용자) | 동명 env |
| `JWT_SECRET` | 랜덤 생성(openssl) | `JWT_SECRET` |
| `DATABASE_URL` | 구성(`postgresql+psycopg://postgres:***@/appdb?host=/cloudsql/<CONN>`) | `DATABASE_URL` |

비밀 아닌 config 는 env 로: `KIS_ENV=real`, `KIS_ACNT_PRDT_CD_STK=01`.

> **안전**: 시크릿 생성·IAM 부여는 사용자가 직접 실행(API 키를 필드에 입력·접근제어 변경은 자동화 대상 아님).
> `.env`·시크릿 값은 이미지·로그·업로드에 미포함(`.dockerignore`/`.gcloudignore` 로 `.env` 제외).

## 배포 / 재배포

코드 수정 후 재배포(소스에서 자동 빌드·기동):

```bash
gcloud run deploy dk-invest-agent \
  --source=. \
  --project=dk-invest-agent-2607122107 \
  --region=asia-northeast3 \
  --allow-unauthenticated \
  --add-cloudsql-instances=dk-invest-agent-2607122107:asia-northeast3:dk-invest-db \
  --set-env-vars=KIS_ENV=real,KIS_ACNT_PRDT_CD_STK=01 \
  --set-secrets=OPENAI_API_KEY=OPENAI_API_KEY:latest,KIS_APP_KEY=KIS_APP_KEY:latest,KIS_APP_SECRET=KIS_APP_SECRET:latest,KIS_ACCOUNT_NO=KIS_ACCOUNT_NO:latest,KIS_ACNT_NO=KIS_ACNT_NO:latest,FRED_API_KEY=FRED_API_KEY:latest,JWT_SECRET=JWT_SECRET:latest,DATABASE_URL=DATABASE_URL:latest \
  --memory=1Gi --cpu=1 --timeout=300 --min-instances=0 --max-instances=3 --quiet
```

- 시크릿 값 변경 시: `printf '%s' "$NEW" | gcloud secrets versions add <NAME> --data-file=-` 후 재배포(`:latest` 자동 반영).
- 스키마는 `create_all` 로만 관리(신규 테이블 추가). 컬럼 변경(alter)이 생기면 Alembic 도입 필요.

## 비용 / 정리

- **Cloud SQL(db-f1-micro)는 스케일-투-제로 불가 → 상시 과금**(무료 체험 크레딧 소진 후 월 ~$8-10). Cloud Run 은
  `min-instances=0` 이라 무트래픽 시 거의 0.
- 전체 정리(과금 중단): `gcloud sql instances delete dk-invest-db` + `gcloud run services delete dk-invest-agent`
  (또는 프로젝트 삭제 `gcloud projects delete dk-invest-agent-2607122107`).
