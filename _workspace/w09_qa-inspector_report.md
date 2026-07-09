# QA 리포트 — WEEK 09 LLM 챗봇 (incremental)

검증 방법론: `invest-qa-checklist` (교차 비교·3중 일관성·안전 grep). incremental — 각 모듈 완성 즉시 검증.

## 착수 전 안전 베이스라인 (2026-07-07, 모두 클린)
- pytest 218 collected / 9 deselected(live) 그린.
- 주문 API grep 0 (히트 2건은 collectors "조회 전용" 명시 주석).
- API 키 하드코딩 0, 모델명(gpt-4o/gpt-5) 하드코딩 0.
- `macro/engine.py`: THRESHOLDS·VIX_PANIC=35·INDICATOR_KEYS·REGIME_PARAMS 존재. CASH_RATIO 별도 상수 없음 → `REGIME_PARAMS.cash` 단일 출처(함정 체크 사전 통과).

---

## 사이클 1 — 작업 #1 INDICATOR_LABELS (macro/engine.py) : 통과 3 / 실패 0

### 통과
1. **INDICATOR_LABELS 존재 + 키 집합 정합** — `macro/engine.py:37-42`. `set(INDICATOR_LABELS) == set(INDICATOR_KEYS)`(yield_spread/hy_spread/vix/fear_greed), 순서도 1:1(경기축→심리축). 한글 라벨 매핑 정확(장단기 금리차/HY 신용스프레드/VIX 변동성/공포탐욕지수).
2. **test-first 증거 + 실행 pass** — `tests/unit/macro/test_indicator_labels.py` 3개(집합 일치·한글 값·순서). `uv run pytest .../test_indicator_labels.py` → 3 passed. 파일 docstring이 "build_criteria_text가 이 상수를 import, 3중 일관성 씨앗"을 명시 — 3중 일관성 소비처를 test-first로 예약.
3. **매크로 회귀 0** — `uv run pytest tests/unit/macro/` → 55 passed. INDICATOR_LABELS 추가로 인한 기존 판정/회귀 손상 없음.

### 관찰 (실패 아님)
- 3중 일관성의 나머지 축(build_criteria_text 출력이 이 상수를 실제 import·반영하는지)은 #3 build_prompt 완성 후 이어서 검증(생산자 측만 완성).
- 전체 스위트 `uv run pytest -q`는 현재 `tests/unit/chat/test_tools.py` collection error(`No module named 'chat.tools'`)로 interrupt됨. 이는 **작업 #2(in_progress)의 test-first Red 상태**(테스트 먼저 작성, 구현 미착지)로 #1과 무관. #2 완성 시 해소 예정. #1 검증에는 macro 서브스위트를 격리 실행해 회귀 확인.

---

## 사이클 2 — 작업 #2 chat/tools.py (팝업 3종 + CHAT_MODEL) : 통과 4 / 실패 0

경계면 #3 **생산자** 측 계약 확정(소비자=프론트 #8 routePopup은 완성 후 1:1 대조).

### 통과
1. **CHAT_MODEL 단일화 (안전)** — `chat/tools.py:16` `CHAT_MODEL="gpt-5.4"` 유일 정의. `grep gpt-5 --include=*.py` 히트는 정의 1줄 + docstring 주석 + 테스트 assert뿐. 모델 문자열 산재 0, gpt-4o 잔재 0.
2. **TOOLS 3종 이름·type** — show_macro_dashboard/show_stock_report/show_watchlist, 전부 `type=function` + description 존재 + parameters.type=object. llm-engineer 통보와 정확 일치.
3. **enum·required 계약** — highlight[regime/cash_ratio/indicators]`:34`, focus[fundamental/technical/both]`:57`, sort_by[registered/change_rate/near_target]`:79`. show_stock_report `required=["ticker"]``:60`.
4. **오발동 방지 + test-first** — 각 description에 "호출하지 않는다" 명시(`:26,47,71`). `test_tools.py` 7개(모델·3종 이름·type·각 enum·required·미호출 문구) → 7 passed.

### 관찰 (실패 아님, 정보)
- `ticker` "6자리"는 description 문자열일 뿐 스키마 pattern 강제 없음(LLM이 채우는 값). 프론트가 `fetchStockBundle(ticker)` 전 6자리 검증을 두면 안전 — 경계면 #3 소비처 검증 시 확인.

---

## 사이클 3 — 작업 #3 chat/build_prompt.py : 통과 6 / 실패 0 (경계면 #4 + 3중 일관성)

### 경계면 #4 — judge_regime 반환 ↔ build_prompt 소비 [양쪽 동시 읽기] : 일치
- 생산자 `macro/engine.py:165-181` `_result`: regime·recommended_cash_ratio·confidence·axes{cycle,sentiment:{score,sign}}·key_drivers[(label,axis,direction)]·params·vix_panic·missing_indicators·raw_data.
- 소비자 `chat/build_prompt.py:59-66`: 위 필드를 정확히 읽음. 필수 3개(regime/recommended_cash_ratio/confidence)는 직접 접근(생산자 항상 제공), 나머지는 `.get()` 방어. **단일축 잔재 votes/override는 읽지 않음**(생산자에도 없음). key_drivers `:39` `(label, axis, direction)` 튜플 언패킹 = 생산자 형태 일치.

### 3중 일관성 — 통과 (하드코딩 임계값 0)
- `build_criteria_text()` 실행 출력이 THRESHOLDS 값을 그대로 반영: 장단기 <0/>0.5, HY >5.0/<3.0, VIX >28/<14, fear_greed <25/>75. VIX_PANIC=35 반영(`:30` f-string 상수 유래). INDICATOR_LABELS 4종 라벨 사용(`:26`).
- 숫자 리터럴 grep: 프롬프트 텍스트 내 판정 임계값은 전부 상수 유래. 예외 2건은 임계값 아님 — `:105` "PER 18"(인용 방법 예시 문구), `:115` "6자리"(티커 길이). `:51` `single_cap==0`은 게이트 판별 로직(params 유래). **하드코딩된 판정 임계값 0.**

### 안전
- 단정표현 grep: `:109` "반드시 오른다/확실하다 ... 쓰지 마라" 금지 지시문 인용만 — 위반 0.
- 면책 고지(시스템 프롬프트): `:83` ①역할 "면허 있는 투자자문 아님" + `:111` ⑤ "참고용, 면허 자문 아님" 상기 — 2곳. (UI 하단은 프론트 #8 검증 시.)
- 필수 6블록 마커 전부 존재(test_prompt_contains_all_six_required_blocks 통과).
- test_build_prompt.py 9개 pass — 3중 일관성 자동회귀(str(VIX_PANIC) in text, THRESHOLDS boundary in text), judgement 주입, 재주입 시 국면 반영. (build_prompt 9 + session 8 = 17, 명세 §#3·#4와 일치.)

### 관찰 (실패 아님, 정보)
- `:105` 예시 "PER 18은 상한을 넘는다"는 회복/확장 per_max=15 기준으론 맞으나 수축=20 기준으론 이하 — 국면 불특정 예시라 오해 여지 미미. 실제 상한은 ④블록 REGIME_PARAMS 주입값을 LLM이 인용. 3중 일관성 위반 아님(임계값 아닌 예시 숫자).

---

## 사이클 4 — 작업 #4 chat/session.py : 통과 3 / 실패 0
- 슬라이딩 윈도우(window=8) `history()` 최근 N개만, `append(user,assistant)` user/assistant만 누적, **시스템·tool 미누적**(토큰 절약·국면 재주입 계약), `reset()`.
- 서버 스토어 `SESSIONS: dict` + `get_session`: 미지 id 생성, 동일 id 인스턴스 재사용(히스토리 누적), 서로 다른 id 격리.
- test_session.py 8개 pass. 계획 §3과 일치, 가짜 테스트·모킹 남용 없음(실제 클래스 실행).

### 전체 스위트: **245 passed / 9 deselected** (그린 복귀 — #2·#3·#4 착지로 이전 collection error 해소)

---

## 사이클 5 — 작업 #8 프론트 ChatPanel·Modal·팝업 라우팅 : 통과 5 / 실패 0 (경계면 #2·#3 소비처)

### 경계면 #3 — TOOLS name ↔ routePopup 분기 [양쪽 동시 읽기] : 1:1 정확 매핑
- 생산자 `chat/tools.py` 3종 name ↔ 소비자 `frontend/src/lib/popupRouter.js:11-15` POPUP_KIND: show_stock_report→stock_report, show_macro_dashboard→macro_dashboard, show_watchlist→watchlist. **죽은 분기 0**, 미지 name·주입성 name(order_stock)은 null 차단(popupRouter.test.js:38 확인).
- args 통과 대조: `ChatPanel.jsx:30` `PopupStockReport ticker={spec.args.ticker} stockName={spec.args.stock_name}` — tools.py의 ticker/stock_name 파라미터명 일치. watchlist는 `args` 통째 전달(sort_by 통과), macro는 자체 조회.

### 경계면 #2 — chat 응답 {text, popups:[{name,args}]} ↔ 프론트 분기 : 소비자 준비 완료
- `ChatPanel.jsx:71-77` runChat: `res.text`→말풍선, `res.popups`→`routePopups(res.popups)`→specs→팝업 자동 오픈. text 없고 팝업만이면 fallback 문구.
- **risk_guardrail 차단(popups:[]/부재)**: `res.popups ?? []` + `routePopups([])→[]`(popupRouter.js:27, test:72) → 팝업 0, 텍스트만. 방어 정상.
- 최종 확정: 생산자 #6 chat.py 반환 shape 착지 후 재대조. 현 시점 소비자 파싱 계약은 tools.py name과 정확 대조됨.

### 안전 (프론트)
- **면책고지 UI 상시** `ChatPanel.jsx:163-165` `chat__disclaimer` → 시스템 프롬프트(build_prompt) + UI 하단 **양쪽** 확보.
- **무캐시**: 팝업 실데이터는 PopupStockReport `fetchStockBundle(ticker)`·RegimeGauge 자체 `fetchMacroRegime`가 열 때마다 직접 조회. ChatPanel messages엔 text/popups만(시세 미저장).
- grep: 주문 API 0, 신규 챗/모달 컴포넌트 hex 0(theme.css 토큰만), 초록·황색 0, `alert/confirm/prompt` 0(Modal.jsx 커스텀 오버레이). 주입성 팝업 name은 routePopup이 null로 차단.
- vitest `npx vitest run` → **3 files, 32 passed**(기존 21 + popupRouter 11). test-first Red 기록(POPUP_KIND={} → 7 실패 → Green) 프론트 명세에 존재.

### 관찰 (실패 아님, 정보)
- show_macro_dashboard의 highlight enum이 args로 통과되나 RegimeGauge는 미사용(W09는 대시보드 통째 표시) — 계획대로. 통과 인자라 무해, W10 활용 여지.

### 후속 regression — ticker 가드 SSOT 통일 (사이클 2 관찰 반영 + 리더 지시) : 통과
- 앞선 관찰(ticker 스키마 pattern 없음)을 frontend가 반영 → 이후 **SSOT로 통일**. 신규 `frontend/src/lib/ticker.js` `TICKER_RE=/^[0-9A-Za-z]{6}$/`(6자 영숫자 — 한국 단축코드 대개 숫자지만 일부 영문 포함, 목적은 종목명·부분입력 차단). **팝업 라우팅(`popupRouter.js:9,26` import)과 직접입력(`StockReport.jsx:100` import)이 동일 규칙 공유** → "직접입력은 받는데 팝업은 거부" UX 불일치 제거(DRY).
- `routePopup:26` stock_report만 `isValidTicker(args.ticker)`로 valid 판정(그 외 valid=true), `ChatPanel.jsx:31-38` `!spec.valid` 시 PopupStockReport 미렌더 → **fetchStockBundle 미호출 + graceful 안내**(환각 ticker로 잘못된 백엔드 조회 차단).
- 테스트: `ticker.test.js`(6자 숫자·영문6자 true, 4자·7자·한글·공백·특수문자·결측 false), `popupRouter.test.js` valid 분기. vitest **4 files 40 passed**(기존 38 + ticker.test 2).

---

## 사이클 6 — 작업 #5 intent.py + #6 chat.py : 통과 8 / 실패 0 (경계면 #7·#2 + risk_guardrail 안전)

### 경계면 #7 — 인텐트 6라벨 ↔ 라우팅 분기 : 일치 (죽은 라벨 없음)
- 생산자 `chat/intent.py:26-33` LABELS 6종(macro_view/stock_analysis/portfolio_advice/watchlist_mgmt/general_qa/risk_guardrail) — test_labels_are_exactly_six 확정.
- 소비자 `chat/chat.py:63`: risk_guardrail만 실질 분기(결정적 차단), 나머지 5라벨은 agent 루프 공통 처리(계획 §3 설계 — 가드레일만 코드 차단, 나머지는 LLM tool_choice=auto가 팝업 결정). 죽은 라벨 없음.

### risk_guardrail 코드결정 — 안전 핵심 : 통과 (LLM 판정 아님)
- `intent.py:70-75` `guardrail_label`: 결정적 정규식 `_GUARDRAIL_RE`(차단 4유형 키워드) → risk_guardrail. **LLM 미개입.** classify가 가드레일을 ML보다 **먼저** 적용(`:104-107`).
- `chat.py:63-65` classify=="risk_guardrail" → **LLM 미호출**, `_GUARDRAIL_MESSAGE` 반환, popups=[]. test_risk_guardrail_blocks_without_calling_llm이 `client.calls == []`로 미호출 실증(빈 FakeClient — 호출 시 IndexError로 강제 검출).
- ③ 과도한 위험은 거절이 아니라 **위험 환기 + 분산 안내로 방향 전환**(`_GUARDRAIL_MESSAGE`에 "분산"·"손실 위험" 포함, test 검증). 면책 고지도 메시지에 포함.
- 모델 부재/오류 시 general_qa 안전 폴백(위험 라벨로 오분류 안 함) — test_classify_falls_back_to_general_qa.

### 경계면 #2 — chat 반환 shape ↔ 프론트 : **양쪽 확정**
- 생산자 `chat.py:111` `return {"text": text, "popups": popups}`, popups=`[{"name":tc.function.name, "args":json.loads(...)}]`(`:92`). 소비자 ChatPanel `res.text`/`res.popups`→routePopups와 정확 일치. risk_guardrail·no-tool_calls·OpenAI 실패 모두 popups=[] → 프론트 routePopups([])→[] 방어와 정합.
- tool_calls args JSON 파싱 실패 시 `{}` graceful(`:90`).

### 안전 (백엔드 LLM 계층)
- 모델명: `model=CHAT_MODEL`(`chat.py:78,102`), gpt-5 문자열 산재 0(정의 1 + docstring/명세 주석만). intent_gen.py도 CHAT_MODEL 상수 참조.
- API 키: `_make_client`가 `openai_api_key()` 환경변수 경유(`:47-49`), 하드코딩 0.
- tool 결과는 `{"ok":True}` 확인만 되먹임(`:99`) — **LLM이 팝업 실데이터·숫자 생성 안 함**(환각 차단). 세션엔 (user, text)만 append.
- 주문 API grep: chat/api 히트는 build_prompt.py:82 "매수·매도 주문 내지 않는다" 금지 명시 프롬프트 — 위반 아님.
- OpenAI 실패 1회 재시도 후 폴백 텍스트(크래시 금지) — test_openai_failure_retries_then_falls_back.

### 자산 확인
- ML 모델 `chat/models/intent_clf.joblib` 산출됨(85KB). 시드 fixture `tests/fixtures/intent_seed.tsv` 존재. 파이프라인 시드 학습→6라벨 예측 스모크 통과. (실데이터셋 data/intent_dataset.tsv는 OPENAI_API_KEY 필요 — 미생성, 계획대로 시드로 모델 산출.)

### 실행: chat 서브스위트 `tests/unit/chat/` → **46 passed**. 경계 mock(OpenAI 클라이언트)만, 내부 조립 로직 실제 실행 — 가짜 테스트·모킹 남용 없음.

---

## 사이클 7 — 작업 #7 api/chat.py (POST /api/chat) : 통과 4 / 실패 0

### 라우터 계약 [양쪽 동시 읽기]
- `api/chat.py:26-33` `POST /api/chat`, body `ChatRequest{session_id, message}`(Pydantic) → `chat(message, judgement, session)` 반환 = `{text, popups}`. 서버 세션 `get_session(body.session_id)`.
- **judgement live 헬퍼 재사용**: `:32` `live_judgement()` = `api/main.py:59-` 헬퍼. main.py의 macro_regime(`:113`)과 **동일 헬퍼 공유**(단일 출처). `live_judgement`는 `collect_macro_indicators(fred_api_key())` 직접 호출(`main.py:64`) → **캐시 미경유(원칙1 라이브)**, 매 요청 최신 국면 계산 → 시스템 프롬프트 주입(국면 변경 자동 반영).
- 순환 참조: `api/chat.py:29` 핸들러 내부 지연 import로 회피(main이 chat_router include).
- `api/main.py:36` CORS `allow_methods=["GET","POST"]`(챗봇 POST), `:86` `include_router(chat_router)` 등록.

### 테스트 (test_chat_route.py, 경계 mock)
- shape {text,popups}·judgement live 계산 후 chat 전달(regime 키 존재)·message 전달, 같은 session_id→같은 Session 인스턴스(서버 세션), GET 405(POST 전용). 3 passed. chat·collect_macro_indicators만 경계 mock, 라우팅/세션/judgement 조립은 실제 실행.

### 전체 스위트 최종: **270 passed / 9 deselected**(백엔드) + 프론트 vitest **40 passed**(4 files). 베이스라인 218 + W09 신규 52.

---

## 최종 안전 검증 (전체 착지 후)
- **주문 API 0**: `grep order_cash|order_rvsecncl|buy_order|sell_order|주문` 실질 히트 0(잔여는 "주문 안 함" 명시 주석/프롬프트).
- **API 키 하드코딩 0**: grep 0, OpenAI/FRED/KIS 전부 `infra.config` 환경변수 경유.
- **모델명 단일화**: CHAT_MODEL="gpt-5.4" 단일 정의, 코드 산재 0, gpt-4o 잔재 0.
- **3중 일관성**: THRESHOLDS/INDICATOR_LABELS/VIX_PANIC → build_criteria_text 생성(하드코딩 판정 임계값 0).
- **면책 고지 양쪽**: 시스템 프롬프트(build_prompt ①·⑤) + UI 하단(ChatPanel 상시).
- **risk_guardrail 코드결정**: 결정적 정규식(LLM 미개입), 차단 시 LLM 미호출(테스트 실증).
- **시세 무캐시**: 팝업 실데이터 프론트 직접 조회, live_judgement 캐시 미경유. LLM은 tool 확인응답만 되먹임(실데이터 생성 안 함).

---

## 최종 판정: 실패 0 / 안전위반 0 / **배포 가능(GO)**

누적 사이클 1~7 통과 39 / 실패 0. 경계면 #2·#3·#4·#7 전부 양쪽 동시 읽기로 교차 확인·정합. 3중 일관성 코드↔프롬프트 강제. 안전 체크리스트(주문 API·API키·모델단일화·면책·무캐시·risk_guardrail 코드결정) 전부 코드+테스트로 관철. 백엔드 270 + 프론트 38 그린 안정.

### 잔여 미검증 (범위 밖·라이브 게이트, 배포 비차단)
- **라이브 e2e**(`-m live`, OPENAI_API_KEY 필요): 실 gpt-5.4 호출로 "삼성전자 어때"→show_stock_report 팝업, "빚내서 몰빵"→차단(LLM 미호출) 스모크. 유닛은 OpenAI mock으로 계약 고정, 실 LLM 문체·tool 발동은 비결정적이라 유닛 대상 아님(계획대로).
- **실 인텐트 데이터셋**(`data/intent_dataset.tsv`): OPENAI_API_KEY로 intent_gen.py 실행 시 생성. 현재는 시드 fixture로 모델(intent_clf.joblib) 산출 — 계획대로. ML 정확도 자체는 비결정적이라 유닛은 인터페이스·가드레일만 고정.
