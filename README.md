# 디케이 투자에이전트 (DK Investment Agent)

**개인 투자자용 금융 분석 AI Agent** — 시장 국면 판정부터 종목 종합리포트, LLM 챗봇, 관심종목 관리까지
하나의 웹앱으로. 연세대학교 정보대학원 · AI핀테크 *[AI핀테크 Agent 분석과 설계]* 과제(WEEK 06~10).

> **핵심 설계 철학 — "판정·수치는 코드가 확정하고, LLM은 설명만 한다."**
> 시장 국면·종목 상태 같은 **판정은 전부 결정적(deterministic) 순수 함수**가 내리고, LLM은 그 결과를 자연어로
> 설명·요약할 뿐이다. **매매 주문 API는 프로젝트 어디에도 없다**(조회·표시만). 위험 요청은 코드 가드레일로
> 차단하고, 외부 콘텐츠(증권사 리포트·영상)는 **출처를 귀속해 인용하고 면책**을 붙인다.

- **스택**: Python 3.13 · FastAPI · SQLAlchemy · scikit-learn · OpenAI · React + Vite · klinecharts
- **배포**: GCP **Cloud Run**(단일 서비스: FastAPI 가 `/api` + 빌드된 React 정적을 같은 오리진 서빙) + **Cloud SQL**(PostgreSQL) + Secret Manager · GitHub Actions(**WIF 키리스**) CI/CD 로 `main` 자동배포
- **테스트**: 백엔드 pytest **899** · 프론트 vitest **375** (hermetic; 실 API 호출은 `-m live` 로만)

---

## 1. 주요 기능

| 영역 | 기능 |
|------|------|
| **시장 국면 판정** | 경기(금리차·신용스프레드) × 심리(VIX·공포탐욕) **2축 매트릭스**로 4국면(회복/확장/과열/수축) 판정 + **역발상 권장 현금비중** · 판정근거 지표 카드(5년 히스토리) · **국면 이동 궤적(족적)** 시각화 |
| **종목 종합리포트** | 현재가·손익·재무비율·추정실적을 **번들 API** 1회 호출로 · 정량요약(CAGR·자기과거평균 PER·RSI·52주) · **예측 PER**(리서치 컨센서스) · **이동평균선 대순환**(고지로 6단계) · 일봉/주봉 × 3개월/1년/3년/10년 선택형 캔들차트 + 대순환 스테이지 리본 |
| **LLM 챗봇** | OpenAI **function calling** agent 루프 · **ML 인텐트 7분류** + 결정적 위험 가드레일 · 서버 세션 · **SSE 실시간 스트리밍** · 포트폴리오 상담 · 마크다운 렌더 |
| **워치리스트** | 관심종목 CRUD · **매수/매도 목표가** 분리 추적 + 능동 알림(도달/근접) · 스파크라인 · 종목 클릭 → 상세 이동 |
| **잔고(포트폴리오)** | 계좌 잔고·평가손익·보유종목(미니차트) — **조회 전용**(무캐시) |
| **증권사 리포트 연계** | 네이버 **애널리스트 리포트** 수집→구조화 요약→종합요약 + **"이 리포트로 상담하기"**(챗 세션 핀) · **시황(매크로) 리포트** 요약·상담·**'금일의 요약'**(최근 5개 종합·중복제거 10줄) · 업로드 PDF **RAG** 검색 · YouTube 자막 요약 |
| **회원제** | 회원가입/로그인(bcrypt·JWT) · **유저별** 관심종목·대화기록 · **유저별 KIS 키**(암호화 저장) · **RBAC + 질문 사용량 한도**(관리자 제어) |
| **기타** | 헤드라인 가입자·방문자수 통계 · 대화기록 저장/삭제/자동명명 · 시황 일별 자동 최신화 |

---

## 2. 스펙 (5주 로드맵 + 확장)

`invest_develop_PLAN.md` 의 5주 로드맵을 완성한 뒤 다수 기능을 확장했다.

| 주차 | 산출물 |
|------|--------|
| **W06** | 데이터 파이프라인 — KIS/FRED/CNN 수집기 · 캐시 3원칙 |
| **W07** | 매크로 국면 엔진 — 2축 판정 + 역발상 현금비중 |
| **W08** | 종목 종합리포트 — 정량요약 엔진 · 번들 API · 캔들차트 |
| **W09** | LLM 챗봇 — 프롬프트 라우팅 · ML 인텐트 · Tool Calling · SSE |
| **W10** | 워치리스트(모듈 3) · 구조화 리포트(Pydantic) |
| **확장** | 시황 요약·챗 상담·금일의 요약 · 국면 이동 궤적 · 이동평균선 대순환 · 선택형 차트 · 회원제(인증·RBAC·한도) · GCP 배포 · CI/CD |

---

## 3. 아키텍처

```
                         ┌──────────────────────────── 브라우저(React + Vite) ───────────────────────────┐
                         │  좌: 상시 채팅(SSE 스트리밍)   |   우: 동적 패널(국면·종목·잔고·관심종목·시황)      │
                         └───────────────────────────────────────┬───────────────────────────────────────┘
                                                                 │ 상대경로 /api (같은 오리진 · CORS 불필요)
   ┌─────────────────────────────────────────── FastAPI (api/) ──┴─────────────────────────────────────────┐
   │                                                                                                        │
   │   chat/  (LLM 계층 — 설명만)         macro/ · stock/  (결정적 판정 엔진 — 코드가 확정)                    │
   │   ├ intent  ML 7분류 + 가드레일       ├ engine.judge_regime  (2축 국면 · 순수함수)                       │
   │   ├ build_prompt  기준표 자동생성      ├ regime_history  (judge_regime 재현 → 궤적)                       │
   │   ├ chat  function calling 루프       └ summary  (정량요약 · 이동평균선 대순환)                          │
   │   └ report / analyst / market_outlook  (Pydantic 구조화 요약 · RAG)                                     │
   │                                                                                                        │
   │   collectors/  (외부 수집)   cache/  (3원칙)   auth/  (인증·RBAC·KIS암호화)   infra/  (DB·설정·병렬)      │
   └────────────────────────────────────────────────────┬───────────────────────────────────────────────┘
        │ KIS · FRED · CNN · 네이버 · YouTube · OpenAP    │ SQLAlchemy
        ▼                                                 ▼
   외부 API / 데이터 소스                          SQLite(로컬) / Cloud SQL PostgreSQL(프로덕션)
```

**계층 원칙**
- **판정은 코드(`macro/`·`stock/`), 설명은 LLM(`chat/`)** — 두 계층을 절대 섞지 않는다.
- **경계 계약**: 프론트는 백엔드 엔드포인트 계약(번들 shape·팝업 툴·판정 스키마)을 그대로 소비한다.
- **환각 차단**: 팝업 실데이터는 LLM 응답이 아니라 **프론트가 직접 조회**하고, 챗 상담 컨텍스트도 **서버가 store 에서 조회**한다(프론트 신뢰전송 없음).
- **캐시 3원칙**: 현재가·잔고 등 **실시간 값은 무캐시**, 확정 과거값·정적 문서만 캐시.
- **3중 일관성(SSOT)**: 임계값·현금비중을 프롬프트에 하드코딩하지 않고 `macro.engine` 상수 한 곳에서 코드·프롬프트·프론트가 파생.

---

## 4. 안전 설계 원칙 (프로젝트의 서명)

1. **매매 주문 API 없음** — 시세·잔고·재무는 *조회만*. 주문·체결·이체 코드는 존재하지 않는다.
2. **판정은 결정적 코드** — 국면·종목 상태(도달/근접/과열 등)는 순수 함수가 결정. LLM은 미개입.
3. **위험 요청 2층 차단** — ① 결정적 키워드 가드레일(단정예측·내부정보·과도위험·시세조종 → LLM 미호출 즉시 차단) ② ML=risk 오탐은 LLM 2차 재분류로 구제/확정.
4. **출처 귀속 + 면책** — 리포트/영상 요약은 "리포트에 따르면"으로 인용하고 면책을 고정 노출(에이전트 자체 판정 아님).
5. **개인정보·시크릿 보호** — 비밀번호 bcrypt 해시만, **KIS 키는 Fernet 암호화** DB 저장(사용 직전 복호화), 통계는 집계만(PII 0), 시크릿은 GCP Secret Manager.

---

## 5. 과제 수행 측면 — 활용 기술

LLM 애플리케이션 **5대 요소**(강의)를 프로젝트에 이렇게 구현했다 → `notebooks/투자에이전트_실행노트북.ipynb` 실행 데모.

| # | 요소 | 구현 | 기술 |
|---|------|------|------|
| 1 | **Intent Classification** | `chat/intent.py` — 7분류 + 결정적 위험 가드레일 | **scikit-learn** `TfidfVectorizer(char_wb, 2–4gram)` + `LogisticRegression`(한글 무형태소) |
| 2 | **Prompt Routing** | `chat/build_prompt.py` — 필수 블록·기준표 자동생성 + `tool_choice=auto` | 상수 SSOT 기반 프롬프트 조립 |
| 3 | **RAG** | `rag/` — PDF 청킹→임베딩→코사인 top-k | **pdfplumber** · OpenAI `text-embedding-3-small` · **numpy** 코사인(FAISS 대신 의존성 절감) |
| 4 | **Tool Calling** | `chat/chat.py`·`chat/tools.py` — 표시 툴/콘텐츠 툴 | OpenAI **function calling** agent 루프 · SSE 스트리밍 tool_call 재조립 |
| 5 | **UI** | `frontend/` — 좌 채팅 + 우 동적 패널 | **React + Vite** · **klinecharts** · react-markdown · SSE |

**그 외 활용 기술**

- **백엔드**: FastAPI · SQLAlchemy 2.0 · Pydantic(구조화 리포트 안전강제) · `uv`(패키지) · `infra.parallel`(ThreadPool 병렬 수집)
- **인증/보안**: bcrypt · PyJWT · **cryptography(Fernet)** KIS 키 암호화 · email-validator
- **데이터**: requests · fredapi · fear-and-greed · pandas · **beautifulsoup4**(네이버 HTML 파싱) · youtube-transcript-api
- **DB**: SQLite(로컬) ↔ **PostgreSQL**(psycopg, 프로덕션) — `DATABASE_URL` 스왑, 방언 중립 ORM
- **프론트**: klinecharts(커스텀 오버레이·대순환 리본) · vitest(jsdom) · 순수 SVG 시각화(국면 궤적·매크로 라인차트·스파크라인)
- **인프라/배포**: Docker(멀티스테이지) · **GCP Cloud Run + Cloud SQL + Secret Manager** · **GitHub Actions + Workload Identity Federation**(키리스 CI/CD)
- **테스트/방법론**: **TDD**(Red→Green) · pytest/vitest · 적대적 다각검증(멀티에이전트 리뷰)

---

## 6. 도움을 얻은 외부 API / 데이터 소스

| API / 소스 | 용도 | 비고 |
|------------|------|------|
| **한국투자증권(KIS) Open API** (`openapi.koreainvestment.com`) | 현재가·손익·재무비율·추정실적·차트·잔고·종목마스터 | OAuth 토큰·좀비토큰 자가치유 · 조회 전용 |
| **FRED** — Federal Reserve Economic Data (`api.stlouisfed.org`) | 장단기 금리차(T10Y2Y)·HY 신용스프레드·VIX 등 매크로 지표 | `fredapi` |
| **CNN Fear & Greed Index** (`production.dataviz.cnn.io`) | 시장 심리(공포탐욕지수) | `fear-and-greed` |
| **Yahoo Finance** (`query1.finance.yahoo.com`) | VIX 보조 | |
| **네이버 증권 리서치** (`finance.naver.com`) | 애널리스트/시황 리포트 목록·PDF | robots 준수·예의 크롤링 |
| **KIS 종목마스터** (`new.real.download.dws.co.kr`) | 종목 검색 자동완성 마스터 | |
| **YouTube Transcript API** | 영상 자막 → 요약 | `youtube-transcript-api`(타임아웃 상한) |
| **OpenAI API** | 챗·요약·구조화(`gpt-5.6-luna`) · RAG 임베딩(`text-embedding-3-small`) | function tools 는 `reasoning_effort='none'` |

> **KIS API 코드는 `kis-code-assistant` MCP 로 검증된 코드를 먼저 검색**해 작성했다.

---

## 7. 실행 방법

### 로컬 (uv)

```bash
uv sync                                             # 백엔드 의존성(.venv)
uv run uvicorn api.main:app --port 8000            # 백엔드
cd frontend && npm install && npm run dev          # 프론트 → http://localhost:5173
```

### 도커 (한 번에)

```bash
docker compose up --build                          # 백엔드 :8000 + 프론트 :5173 (.env 런타임 주입)
```

### 환경 변수 (`.env`, `.env.example` 참고)

`OPENAI_API_KEY` · `FRED_API_KEY` · `KIS_APP_KEY`/`KIS_APP_SECRET`/`KIS_ACCOUNT_NO` · `JWT_SECRET` · `KIS_ENC_KEY`(Fernet) · `DATABASE_URL`(선택) — **키는 커밋하지 않는다**(gitignore).

### 테스트

```bash
uv run pytest                    # 백엔드 899 (라이브 제외; 실 API 는 -m live)
cd frontend && npm test          # 프론트 375 (vitest)
```

### 과제 실행 노트북

```bash
uv run --with jupyterlab jupyter lab notebooks/투자에이전트_실행노트북.ipynb
```

### 프로덕션 배포

`main` 푸시 → GitHub Actions(WIF) 가 테스트 후 **GCP Cloud Run** 에 자동배포. 수동 배포·인프라 셋업은
`DEPLOY_GCP.md` 참고.

---

## 8. 디렉토리 / 문서 지도

기능별 상세 지식(결정·함정·계약)은 각 디렉토리 `CLAUDE.md` 에 있다.

```
api/          FastAPI 엔드포인트(= AWS Lambda 로컬 스탠드인)
macro/        국면 판정 엔진(결정적·LLM 미개입) + 궤적 재현
stock/        종목 정량 요약 · 이동평균선 대순환
chat/         LLM 계층(인텐트·프롬프트·챗·구조화 요약·RAG 연계) — 설명만
rag/          업로드 PDF RAG(pdfplumber · 임베딩 · numpy 코사인)
collectors/   외부 수집기(KIS·FRED·CNN·네이버·YouTube)
cache/        캐시 3원칙(무캐시/확정과거 캐시)
auth/         인증·RBAC·질문 한도·유저별 KIS 키 암호화
watchlist/    관심종목(목표가·알림·유저 스코프)
infra/        DB(SQLAlchemy)·설정·병렬·암호화·사이트 통계
frontend/     React + Vite(좌 채팅 + 우 동적 패널)
notebooks/    과제 실행 노트북(5요소 데모 + 결정적 엔진 재사용 보너스)
```

- **루트 문서**: `CLAUDE.md`(설계 원칙·변경 이력) · `DOCKER.md`(로컬 도커) · `DEPLOY_GCP.md`(GCP 배포·CI/CD) · `invest_develop_PLAN.md`(원본 스펙)

---

## 면책

이 프로젝트는 **교육용 과제**이며 투자 자문·매매 권유가 아니다. 모든 판정·요약은 참고용이고, 투자 판단과
그 결과는 전적으로 본인 책임이다. 매매 주문 기능은 구현되어 있지 않다.
