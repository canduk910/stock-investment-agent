# W09 llm-engineer — LLM 챗봇 백엔드 (프롬프트·팝업·세션·ML 인텐트·agent 루프·라우터)

작업 #1~#7. TDD(Red→Green→Refactor). LLM 출력은 비결정적이라 미검증 — 그 주변의 결정적
코드(기준표 상수 포함·text/popups 분리·세션 윈도우·가드레일·라우트 계약)만 테스트로 고정.
전체 스위트 **270 passed**(기존 218 + 신규 52), 9 deselected(live).

## 테스트 목록(스펙 근거) → 구현 순서 (test-first 증거)

의존 순서대로 각 모듈 Red(실패 확인)→Green(최소 구현)→전체 회귀. 각 테스트 이름 접미사에
스펙 근거를 남김(예 `__triple_consistency`, `__frontend_contract`, `__deterministic`).

### #1 macro/engine.py `INDICATOR_LABELS` (tests/unit/macro/test_indicator_labels.py, 3)
- 라벨 키집합 == INDICATOR_KEYS(누락·잉여 0) / 한글 라벨 값 / 순서 1:1(경기축→심리축).
- 근거: 스킬 §1 build_criteria_text 가 import 하는 3중 일관성 씨앗. 기존 매크로 55 tests 회귀 유지.

### #2 chat/tools.py 팝업 3종 + CHAT_MODEL (tests/unit/chat/test_tools.py, 7)
- CHAT_MODEL == "gpt-5.4"(모델 ID 단일 출처) / 3종 이름 집합 / type=function / 각 enum·required /
  description 에 "호출하지 않는다" 존재(오발동 방지). 근거: 스킬 §2, 프론트 라우팅 계약(QA #2·#3).

### #3 chat/build_prompt.py (tests/unit/chat/test_build_prompt.py, 9) [#1 의존]
- build_criteria_text: `str(VIX_PANIC) in text`, 모든 INDICATOR_LABELS·THRESHOLDS 경계문자열 포함,
  `"> {VIX_PANIC}"` 생성(하드코딩 아님) → **3중 일관성 자동 회귀**.
- build_prompt: 필수 6블록 마커(국면 판정 출처 고정/자동매매/면허/기준표/단정/손실/팝업), judgement의
  regime·현금비중·confidence·vix_panic·params 주입, 재주입 시 국면 변경 반영. 근거: 스킬 §1.

### #4 chat/session.py (tests/unit/chat/test_session.py, 8)
- 빈 히스토리 / user→assistant append / user·assistant 롤만 / window 초과 잘림 / reset /
  get_session 신규생성·동일인스턴스·id격리. 근거: 계획 §3, 골격 §3. 시스템·tool 미누적.

### #5 chat/intent.py + intent_gen.py + intent_train.py (tests/unit/chat/test_intent.py, 15)
- (a) 가드레일 차단 4유형 8예문 → risk_guardrail(결정적, 모델 불필요) / 비위험 → None
- (b) 가드레일이 ML 우선(“삼성전자 빚내서 몰빵”→risk) / 모델 실패해도 가드레일 동작
- (c) build_pipeline 시드학습→예측 라벨 ⊂ 6라벨(스모크) / (d) classify 항상 유효 라벨·모델부재 general_qa 폴백 / 6라벨 정확.
- 근거: 계획 §4, 스킬 §3(risk_guardrail 최우선·보수적 귀속).

### #6 chat/chat.py agent 루프 (tests/unit/chat/test_chat.py, 7)
- tool_calls→popups[0].name·args 분리·text 분리·create 2회 / no tool_calls→popups=[] /
  first create 에 model=gpt-5.4·tool_choice=auto·TOOLS·system(judgement 주입) /
  risk_guardrail→LLM 미호출(calls=[])·차단텍스트·popups=[]·분산안내 / 세션 append(정상·차단 모두) /
  OpenAI 실패→1회 재시도 후 폴백("일시")·크래시 없음. 근거: 계획 §5, 골격 §1. OpenAI mock(경계).

### #7 api/chat.py POST /api/chat (tests/unit/api/test_chat_route.py, 3)
- 응답 shape {text,popups} / 같은 session_id→동일 Session(서버 세션) / GET 405(POST 전용).
- 근거: 계획 §6. chat.chat·collect_macro_indicators 경계 mock(실 LLM/키 불요).

## 팝업 툴 스키마 (chat/tools.py — 프론트 라우팅 계약)

| 툴 name | 파라미터(enum) | required |
|---|---|---|
| `show_macro_dashboard` | `highlight`: regime \| cash_ratio \| indicators | — |
| `show_stock_report` | `ticker`(6자리 문자열), `stock_name`, `focus`: fundamental \| technical \| both | `ticker` |
| `show_watchlist` | `sort_by`: registered \| change_rate \| near_target | — |

각 description 에 "언제 호출/호출하지 않는지" 명시. LLM 은 "무엇을 띄울지"만 결정, 실데이터는
프론트가 API 직접 조회(환각 차단).

## chat 응답 shape (프론트 계약)

```json
{ "text": "말풍선 텍스트(빈 문자열 가능)",
  "popups": [ {"name": "show_stock_report", "args": {"ticker": "005930"}} ] }
```
- risk_guardrail 차단: text=차단 안내문, popups=[] (LLM 미호출).
- OpenAI 실패: text="…일시적으로 답변을 생성할 수 없습니다…", popups=[] (200 정상, 크래시 없음).
- POST /api/chat body: `{session_id, message}`. session_id 별 서버 세션 히스토리 보관(슬라이딩 window=8).

## CHAT_MODEL

`chat/tools.py::CHAT_MODEL = "gpt-5.4"` — 모델 ID 단일 출처(사용자 오버라이드: gpt-4o 아님).
챗봇(chat.py)·데이터 생성(intent_gen.py) 모두 이 상수만 참조. grep 검증: `gpt-` 하드코딩은
tools.py 1곳뿐(코드 산재 0).

## 인텐트 라벨·가드레일 규칙

6라벨: `macro_view, stock_analysis, portfolio_advice, watchlist_mgmt, general_qa, risk_guardrail`.
- **결정적 키워드 가드레일이 ML 보다 우선**(chat/intent.py `guardrail_label`). 정규식 키워드:
  ① 단정 예측(반드시/무조건/확실히 오르, 떡상 확실) ② 내부정보(내부정보, 미공개 정보)
  ③ 과도한 위험(몰빵, 빚내서, 대출 받아서, 전재산, 풀매수) ④ 시세조종(작전주, 시세조종, 주가조작).
  매치 시 무조건 risk_guardrail(경계 사례 보수적 귀속). **차단은 코드가 결정, LLM 판정 아님.**
- classify(text): 가드레일 → ML predict → 유효라벨 검증. 모델 부재/오류는 general_qa 폴백(비위험).
- chat.py: risk_guardrail → 결정적 차단 안내(LLM 미호출, popups=[]). ③ 위험은 거절이 아니라
  위험 환기 + 분산 안내로 방향 전환(스킬 §3). 안내문에 면책 고지 포함.

## ML 파이프라인 명세

- **build_pipeline()**(chat/intent.py, 단일 출처): `TfidfVectorizer(analyzer="char_wb", ngram_range=(2,4))`
  + `LogisticRegression(max_iter=1000)`. 한글을 형태소 분석기 없이 char n-gram 으로 벡터화.
  학습 스크립트·런타임·테스트가 이 함수를 공유.
- **intent_gen.py**(비결정적·유료, LLM 호출): gpt-5.4(CHAT_MODEL)로 라벨별 균형 질문 생성 →
  `data/intent_dataset.tsv`(`질문<TAB>라벨`). 라벨별 브리프에 라우팅 의도·차단 4유형 예시 명시.
  실행 `uv run python -m chat.intent_gen [라벨당_개수]`. **OPENAI_API_KEY + 유효 모델 접근 필요.**
- **intent_train.py**(결정적·오프라인): 데이터셋 TSV → build_pipeline 학습 → `chat/models/intent_clf.joblib`.
  우선순위: data/intent_dataset.tsv 있으면 그것으로, 없으면 tests/fixtures/intent_seed.tsv(라벨당 소수)로.
  실행 `uv run python -m chat.intent_train`.
- **커밋 모델 상태(2026-07-09 갱신 — #10 사용자 승인 실행 완료)**: `chat/models/intent_clf.joblib` 는
  **gpt-5.4 로 생성한 실데이터셋 `data/intent_dataset.tsv`(360행 = 6라벨 × 60, 완전 균형·중복 0·
  형식위반 0·미지라벨 0)로 재학습**한 모델(617KB). intent_gen.py→intent_train.py 순 실행, 전체
  270 passed 회귀 유지. 수동 분류 12/13 일치(가드레일 4유형 전건 정확). 단 1건 "PER이 뭐야"→
  stock_analysis(기대 general_qa) 오분류는 char n-gram 경계 모호성 — **두 라벨 모두 비차단(LLM
  경로)이라 안전 무관**(LLM 이 용어 설명 여부를 결정, 프롬프트가 처리). ML 정확도 비결정성은
  계획·QA 방법론상 인정 범위. gpt-5.4 모델 ID 는 OpenAI 에서 유효 확인(ping→pong, json 모드 정상).
- 이전 시드 fixture(56샘플) 모델은 위 실데이터 모델로 교체됨(파이프라인 정의 불변 — build_pipeline).

## 안전 체크 (grep 검증 완료)
- 주문 API 호출 0(chat/·api/chat.py). build_prompt 의 "매수·매도 주문 내지 않는다"는 안전 지침 텍스트.
- 프롬프트 하드코딩 임계값 숫자 0(전부 build_criteria_text 상수 유래) · 모델 문자열 산재 0(tools.py 1곳) ·
  API 키 하드코딩 0(infra.config.openai_api_key 환경변수) · 면책 고지 프롬프트+차단 안내 포함.
- risk_guardrail 차단은 코드 결정(LLM 미호출) · 팝업 실데이터는 프론트 직접 조회(LLM 숫자 생성 0).

## 신규/수정 파일
- 신규: chat/{tools,build_prompt,session,intent,intent_gen,intent_train,chat}.py, chat/models/intent_clf.joblib,
  api/chat.py, tests/fixtures/intent_seed.tsv, tests/unit/chat/test_*.py, tests/unit/api/test_chat_route.py,
  tests/unit/macro/test_indicator_labels.py
- 수정: pyproject.toml(openai·scikit-learn·joblib), macro/engine.py(INDICATOR_LABELS),
  api/main.py(_map_engine_input·live_judgement 추출·chat_router 등록·POST CORS)

## 라이브 스모크 (미실행 — 키+실행환경 필요, 계획 §검증3)
`OPENAI_API_KEY` + gpt-5.4 접근 시: POST /api/chat "삼성전자 어때"→show_stock_report+text /
"지금 시장 어때"→show_macro_dashboard / "빚내서 몰빵"→차단(LLM 미호출). 단위 테스트는 OpenAI
mock 으로 이 분기를 모두 커버.
