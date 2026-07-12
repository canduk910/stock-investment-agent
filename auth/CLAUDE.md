# auth/ — 인증 (회원가입/로그인)

유저별 데이터(관심종목·대화기록)의 스코프 진입점. **자체 JWT**(관리형 auth 비의존 → GCP Cloud Run 이식).

- **비밀번호는 bcrypt 해시(`password_hash`)만** 저장한다(`models.User`). 평문 저장·로깅·응답 노출 절대 금지. `security.hash_password`/`verify_password`(예외는 False=안전).
- **JWT(HS256)** — `security.create_access_token(user_id)`(sub=user_id, exp 7일)·`decode_token`(만료·서명·형식 오류는 None). 시크릿은 env `JWT_SECRET`(미설정 시 개발용 기본값 ≥32B — **프로덕션 필수 설정**). 시크릿 값 로깅 금지.
- **`deps.get_current_user`** = FastAPI 의존성: `Authorization: Bearer <jwt>` → `decode_token` → `db.get(User, id)`. 토큰 부재·무효·유저 없음은 **401**. 유저별 라우트가 `user: User = Depends(get_current_user)`로 스코프한다(user.id 를 문자열화해 store user_id 로 사용).
- 라우트 `api/auth.py`: `POST /api/auth/signup`(email+password≥8 → 해시 저장 → JWT; 중복 email=409·약한 비번=422)·`POST /api/auth/login`(검증 → JWT; 불일치=401)·`GET /api/auth/me`(Bearer → {id,email}). email 은 소문자 정규화.
- **email 검증**은 `pydantic.EmailStr`(dep `email-validator`).
- 테스트: 인메모리 SQLite + `app.dependency_overrides[get_db]`(세션 주입)로 라우트 계약 검증(실 DB 불요). 유저별 라우트 테스트는 `dependency_overrides[get_current_user]`로 고정 유저 주입.
