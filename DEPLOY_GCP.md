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
| `OPENAI_API_KEY` `FRED_API_KEY` | 로컬 `.env`(사용자) | 동명 env |
| `JWT_SECRET` | 랜덤 생성(openssl) | `JWT_SECRET` |
| `KIS_ENC_KEY` | 랜덤 생성(Fernet) — **KIS 자격증명 암호화 마스터키** | `KIS_ENC_KEY` |
| `DATABASE_URL` | 구성(`postgresql+psycopg://postgres:***@/appdb?host=/cloudsql/<CONN>`) | `DATABASE_URL` |

비밀 아닌 config 는 env 로: `KIS_ENV=real`, `KIS_ACNT_PRDT_CD_STK=01`.

> **KIS 앱키는 Secret Manager 에 없다** — 유저별로 앱 '설정'에서 등록해 **암호화 DB 저장**하고(사용 시 복호화),
> 미등록 유저는 **`__shared__` 암호화 행**(1회 시드)을 공유 fallback 으로 쓴다. 상세는 아래 "KIS 자격증명 마이그레이션".
> **안전**: 시크릿 생성·IAM 부여는 사용자가 직접 실행. `.env`·시크릿 값·복호화 KIS 자격증명은 이미지·로그·응답·업로드에 미포함.

## KIS 자격증명 마이그레이션 (공유키 제거 → 유저별 암호화 DB)

KIS 앱키를 전 유저 공용(Secret Manager)에서 **유저별 암호화 DB 저장**으로 옮겼다. 우선순위:
**본인 등록키(DB `scope_key=str(user.id)`) → 공유(`__shared__` DB 행) → env(`.env`, 로컬 개발)**.
암호화는 Fernet(`infra/encryption.py`), 마스터키 `KIS_ENC_KEY`. 토큰 캐시는 app_key 해시로 격리(유저 키 상호 무간섭).

**프로덕션 전환(1회, 완료됨):**
1. `KIS_ENC_KEY`(Fernet) 생성 → Secret Manager 등록(사용자).
2. **전환 배포**: `KIS_ENC_KEY` + 기존 `KIS_APP_KEY/SECRET/ACCOUNT_NO/ACNT_NO` 유지 → startup `seed_shared_kis_from_env()`
   가 env → `__shared__` 암호화 행을 Cloud SQL 에 1회 시드(idempotent).
3. **KIS 앱키 시크릿 제거 + 재배포**: `gcloud secrets delete KIS_APP_KEY KIS_APP_SECRET KIS_ACCOUNT_NO KIS_ACNT_NO`,
   `--set-secrets` 에서도 제거(아래 배포 명령이 최종형). env 에 KIS 앱키 없어도 `__shared__` 행이 공유 fallback.

유저 등록 API: `POST/GET/DELETE /api/me/kis-credentials`(인증). POST 는 실제 KIS 토큰 발급으로 검증 후 암호화 저장.
GET 은 마스킹 상태만. 프론트 '설정' 탭(`KisSettingsPanel`).

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
  --set-secrets=OPENAI_API_KEY=OPENAI_API_KEY:latest,FRED_API_KEY=FRED_API_KEY:latest,JWT_SECRET=JWT_SECRET:latest,KIS_ENC_KEY=KIS_ENC_KEY:latest,DATABASE_URL=DATABASE_URL:latest \
  --memory=1Gi --cpu=1 --timeout=300 --min-instances=0 --max-instances=3 --quiet
```

- 시크릿 값 변경 시: `printf '%s' "$NEW" | gcloud secrets versions add <NAME> --data-file=-` 후 재배포(`:latest` 자동 반영).
- 스키마는 `create_all` 로만 관리(신규 테이블 추가). 컬럼 변경(alter)이 생기면 Alembic 도입 필요.

## 비용 / 정리

- **Cloud SQL(db-f1-micro)는 스케일-투-제로 불가 → 상시 과금**(무료 체험 크레딧 소진 후 월 ~$8-10). Cloud Run 은
  `min-instances=0` 이라 무트래픽 시 거의 0.
- 전체 정리(과금 중단): `gcloud sql instances delete dk-invest-db` + `gcloud run services delete dk-invest-agent`
  (또는 프로젝트 삭제 `gcloud projects delete dk-invest-agent-2607122107`).
