# auth/ — 인증 (회원가입/로그인)

유저별 데이터(관심종목·대화기록)의 스코프 진입점. **자체 JWT**(관리형 auth 비의존 → GCP Cloud Run 이식).

- **비밀번호는 bcrypt 해시(`password_hash`)만** 저장한다(`models.User`). 평문 저장·로깅·응답 노출 절대 금지. `security.hash_password`/`verify_password`(예외는 False=안전).
- **JWT(HS256)** — `security.create_access_token(user_id)`(sub=user_id, exp 7일)·`decode_token`(만료·서명·형식 오류는 None). 시크릿은 env `JWT_SECRET`(미설정 시 개발용 기본값 ≥32B — **프로덕션 필수 설정**). 시크릿 값 로깅 금지.
- **`deps.get_current_user`** = FastAPI 의존성: `Authorization: Bearer <jwt>` → `decode_token` → `db.get(User, id)`. 토큰 부재·무효·유저 없음은 **401**. 유저별 라우트가 `user: User = Depends(get_current_user)`로 스코프한다(user.id 를 문자열화해 store user_id 로 사용).
- 라우트 `api/auth.py`: `POST /api/auth/signup`(email+password≥8 → 해시 저장 → JWT; 중복 email=409·약한 비번=422)·`POST /api/auth/login`(검증 → JWT; 불일치=401)·`GET /api/auth/me`(Bearer → {id,email}). email 은 소문자 정규화.
- **email 검증**은 `pydantic.EmailStr`(dep `email-validator`).
- 테스트: 인메모리 SQLite + `app.dependency_overrides[get_db]`(세션 주입)로 라우트 계약 검증(실 DB 불요). 유저별 라우트 테스트는 `dependency_overrides[get_current_user]`로 고정 유저 주입.
- **`deps.get_current_user_optional`**: Bearer 있으면 User, 없거나 무효면 **None(401 안 냄)**. 공개 유지 라우트(잔고·종목번들·리포트)가 "로그인+등록 시 본인 KIS 키, 아니면 공유 fallback"을 쓰게 하는 옵션 인증.

## 유저별 KIS 자격증명 (암호화 저장)
- **공유키 폐기 → 유저별 암호화 DB**: `kis_models.KisCredentialRow(scope_key unique = str(user.id)|"__shared__", app_key/secret/account 암호문 + acnt_prdt_cd·env)`. import_models 등록. **DB엔 Fernet 암호문만**(`infra/encryption.py`, 마스터키 `KIS_ENC_KEY`), 복호화는 `kis_store` 에서만·사용 직전 in-memory(로깅·응답 금지).
- **`kis_store.KisCredentialStore(db)`**(SqlWatchlistStore 패턴): `resolve(user_id)` = 본인 → `__shared__` 순 (KisCreds, source) · `upsert_encrypted`(CANO 하이픈 파싱) · `delete` · `status`(마스킹만, 복호화 원문 금지). 클라이언트 조립은 `api.detail.resolve_kis_client(user, db)`(본인→공유→env fallback→NoKisCredentials).
- **API `api/kis_credentials.py`**: `POST /api/me/kis-credentials`(인증) — 실제 KIS 토큰 발급으로 **검증 후** 암호화 저장(실패 400, 키값 미노출). `GET`(마스킹 상태) · `DELETE`(삭제→공유 fallback).
- **공유 fallback**: `auth/kis_seed.seed_shared_kis_from_env()`(startup)가 env KIS_* → `__shared__` 암호화 행 1회 시드(idempotent·graceful). 로컬은 `.env`(3순위)도 fallback. 프로덕션은 시드 후 Secret Manager 의 KIS 앱키 제거.
