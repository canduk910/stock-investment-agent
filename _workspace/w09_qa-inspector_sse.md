# QA 리포트 — WEEK 09 SSE 실시간 스트리밍 (incremental)

검증 방법론: `invest-qa-checklist`(교차 비교·3중 일관성·안전 grep). 승인 계획:
`week-09-velvety-quiche.md`. 기존 논스트림 W09(사이클 1~7, `w09_qa-inspector_report.md`
= GO)는 회귀 기준 — SSE는 그 위에 **병행 추가**(기존 `chat()`/`POST /api/chat` 불변).

## 착수 전 안전 베이스라인 (2026-07-09, 클린)
- 주문 API grep(`order_cash|order_rvsecncl|buy_order|sell_order`, .venv 제외): 실질 0.
- API 키 하드코딩 0.
- CHAT_MODEL="gpt-5.4" 단일(`chat/tools.py:16`), gpt-4o 잔재 0(주석의 "gpt-4o 아님" 부정 표현뿐).
- 기존 프론트 vitest 40 passed(회귀 무손상). 기존 백엔드 270(논스트림)은 SSE 착지 후 재확인.

## SSE 이벤트 계약 — 양쪽 테스트 교차 확인 (생산자↔소비자 단일 출처)

| 이벤트 | 백엔드 생산 (test_chat_stream.py) | 프론트 소비 (sseChat.test.js) | 정합 |
|---|---|---|---|
| stage | `{type:stage, stage:analyze/generate/summarize}` | `onStage('analyze')` | ✓ |
| token | `{type:token, text}` | `onToken('안녕')` | ✓ |
| popups | `{type:popups, popups:[{name,args}]}` | `onPopups([{name,args}])` | ✓ |
| done | `{type:done, popups:[...]}` | `onDone([...])` | ✓ |

- stage enum: `analyze`/`generate`/`summarize`는 `chat_stream`이, `regime`은 라우트(#13)가 주입
  (test_chat_stream L186 주석 + sseChat.js L6 주석에 양쪽 명시). `regime` 소비는 라우트 착지 후 재확인.
- popups shape `[{name,args}]`는 기존 `routePopups`(popupRouter.js) 소비 계약과 동일 →
  `done`의 popups를 그대로 `routePopups`에 넘기면 기존 팝업 라우팅 재사용 가능(#15에서 확인).

---

## 사이클 1 — #12 chat_stream()·_accumulate_tool_calls + #14 sseChat.js : 통과 / 실패 0

### 백엔드 #12 (chat/chat.py:114-255)
- **8/8 green** (`tests/unit/chat/test_chat_stream.py`).
- **안전 — guardrail LLM 미호출(최우선)**: `chat.py:169-173` classify=="risk_guardrail" →
  차단 token + done(popups=[]), LLM 미호출. `test_guardrail_blocks_without_calling_llm`이
  빈 `_FakeStreamClient([])`로 `client.calls==[]` 실증(호출 시 IndexError로 강제 검출). **결정적 차단 유지.**
- **팝업은 tool_calls만**: `_accumulate_tool_calls`(L114)가 index별 name/arguments 조각 재조립 →
  `popups` 이벤트. 실데이터 생성 없음(프론트 조회). 깨진 JSON은 `{}` 방어(L142-145).
- **tool 되먹임 확인응답만**: `_assistant_tool_calls_message` + tool role `{"ok":True}`(L219) —
  LLM에 실데이터/숫자 미전달(환각 차단, 기존 chat()과 동일 정신).
- **stream=True**: 호출#1·#2 모두 stream=True, model=CHAT_MODEL(L188,224). 하드코딩 모델 문자열 0.
- **폴백**: 예외 시 `_FALLBACK_MESSAGE` token + done, `session.append`(L233). guardrail/정상/예외 중
  **정확히 한 경로만** session.append(예외 시 return으로 종료 → 이중 append 없음). 확인 완료.
- **CHAT_MODEL·TOOLS·classify·build_prompt·session 전부 기존 재사용**(신규 상수·숫자 0).

### 프론트 #14 (frontend/src/lib/sseChat.js)
- **12/12 green** (`sseChat.test.js`, 기존 40 무손상).
- `parseSSEBuffer` 순수함수: `\n\n` 경계 재조립, 청크 가로지름/여러이벤트 한청크/한글 멀티바이트
  경계/keep-alive 주석/깨진 JSON 조용히 스킵 — 전부 커버.
- `readChatStream`: getReader 루프 + TextDecoder(stream:true, UTF-8 경계 방어), 핸들러 선택적
  (누락 크래시 없음), ok=false/body 없음 → onError(무한 대기 금지).
- **하드코딩 hex 0**(파싱 로직뿐, 스타일 없음).

---

---

## 사이클 2 — #13 SSE 라우트 POST /api/chat/stream (api/chat.py) : 통과 / 실패 0

### 전체 스위트: **281 passed / 9 deselected**(기존 270 + SSE 신규 11). 회귀 0.
- test_chat_stream_route.py 3/3 + test_chat_stream.py 8/8. 기존 test_chat_route.py(논스트림) green 유지.

### 안전 (스트리밍 경로)
- **guardrail 시 live_judgement 미실행(시세 무낭비·무캐시)**: `_sse` L74 `classify(body.message)=="risk_guardrail"`
  → judgement={} 로 두고 live_judgement 건너뜀, regime stage 미주입(L76-79).
  `test_stream_guardrail_skips_regime_stage`가 `calls["live"]==0` + `"regime" not in stages` 실증.
  **라우트가 실제 classify를 호출**(mock 아님) — 가드레일 결정을 코드가 라우트 진입점에서도 한 번 더 방어.
- **live_judgement 캐시 미경유**: `api/main.py:59-67` `collect_macro_indicators(fred_api_key())` 직접 호출
  (캐시 미경유, 원칙1). SSE 라우트가 논스트림과 **동일 헬퍼 재사용** → 시세 무캐시 불변.
- **헤더**: `Cache-Control:no-cache` + `X-Accel-Buffering:no`(L98) — 테스트 검증(프록시 버퍼링 방지).
- **ensure_ascii=False**(L68): 한글 토큰 SSE 프레임 정상 직렬화.
- **stage enum SSOT**: analyze/regime/generate/summarize 산재 검사 — 계약 밖 stage 문자열 0.

### 경계면 — 이벤트 순서·중복 제거
- 정상: analyze(라우트)→regime(라우트, FRED 조회 타이밍)→generate(chat_stream)→…→done.
  chat_stream 선두 analyze는 라우트가 L83-84로 **중복 제거**. test가 `stages==["analyze","regime","generate"]` +
  judgement 전달 + 세션 재사용(동일 id) 실증.

### mock 없는 실코드 실증 (리더 지시 — llm-engineer-2 주장 직접 검증)
실제 `_sse` + 실제 classify 통과, live_judgement만 카운터 래핑(chat_stream만 mock, LLM 회피):
- 실제 classify: "빚내서 몰빵할까"→risk_guardrail, "반드시 오르는 종목"→risk_guardrail,
  "삼성전자 어때"→stock_analysis, "지금 시장 어때"→macro_view (guardrail 정확).
- **guardrail("빚내서 몰빵"): live_judgement 호출 0회, regime stage 미주입** — FRED 낭비 없음 실증.
- 비-guardrail("삼성전자 어때"): live_judgement 1회, regime stage 주입 — 정상 흐름 실증.
- 논스트림 회귀: `test_chat.py`(7) + `test_chat_route.py`(3) = **10 passed**, 기존 chat()·/api/chat 불변.
- 팝업 tool_calls만: `popups`는 `_accumulate_tool_calls`(chat.py:209)에서만 생성, guardrail/폴백은
  항상 `popups:[]`(L172,235) — tool_calls 없이 팝업 생성 경로 0.

### 관찰 (실패 아님)
- **이중 classify**: 라우트 `_sse`(L74)와 `chat_stream` 내부(chat.py:169)가 각각 classify 호출. 결정적
  함수라 결과 동일 → 정합성 문제 없음. guardrail을 라우트에서 먼저 판정해 live_judgement 낭비 회피(의도).
  classify는 로컬 joblib 추론이라 비용 미미.

---

## 사이클 3 — #15 프론트 통합(api.js·ChatPanel·ChatMessage·chatStages·styles) : 통과 / 실패 0

### 전체 프론트: **vitest 60 passed / 6 files**(기존 40 + sseChat 12 + chatStages + valid 등). build 0 error.

### 경계면 #2·#3 재사용 [양쪽 동시 읽기] : done popups → routePopups 정합
- `postChatStream`(api.js): fetch 자체 실패도 try/catch로 onError 유도(폴백). `readChatStream`에 handlers 위임.
- `ChatPanel.onDone`→`finishStream(popups)`(L87-100)→`routePopups(popups)`→specs→모달 자동 오픈.
  **SSE done의 popups shape `[{name,args}]`가 기존 routePopups 소비 계약과 동일** → 팝업 라우팅·ticker
  valid 게이트(routePopup) 그대로 재사용. ChatMessage도 `routePopups`로 "다시 열기" 칩 렌더(일관).
- **stage enum SSOT**: `chatStages.js` STAGES(analyze/regime/generate/summarize) = 백엔드 stage 계약 1:1.
  라벨: 질문 분석/시장 국면 조회/답변 작성 중/정리 중(계획 일치). 미지 stage 방어(idx<0→0).

### 안전 (프론트 스트리밍)
- **환각차단·무캐시 불변**: SSE token/popups 경로에서 시세·실데이터 추출 **0**(grep). 팝업 실데이터는
  여전히 `PopupStockReport`(fetchStockBundle)·`RegimeGauge`(fetchMacroRegime)가 열 때마다 직접 조회.
  LLM/SSE가 시세를 흘리는 경로 없음.
- **면책 고지 상시**: `chat__disclaimer`(ChatPanel:229-231) 유지 — 시스템 프롬프트 + UI 하단 양쪽.
- **하드코딩 hex 0**: 신규 chat 스트리밍 코드(ChatPanel/ChatMessage/chatStages/sseChat) hex 0.
  styles.css chat 스트리밍(1001-1066): 완료=`--c-blue-strong`·현재=`--c-blue`·대기=`--c-text-muted`·
  커서=`--c-blue`(theme.css 토큰만). 초록·황색 0.
- **무한 스피너 금지**: 스트림 실패→`runChatFallback` 논스트림 폴백 1회(`fellBack` 가드 중복방지),
  폴백도 실패→placeholder 제거 + 에러 배너 + 재시도(lastQueryRef). streaming 중 입력 비활성
  (`disabled={loading||!input.trim()}`). 토큰 갱신마다 자동 스크롤(useEffect [messages]).

### 관찰 (실패 아님)
- `finishStream`/`patchLastBot`은 마지막 메시지가 `role==='bot' && streaming`일 때만 갱신 → 레이스
  방어(placeholder 없으면 no-op). 폴백은 placeholder 있으면 교체, 없으면 append(양쪽 방어).

---

---

## 사이클 4 — Docker e2e 라이브 스모크(실 gpt-5.4, curl) : 통과

컨테이너 기동 확인(`docker compose ps`): sia-backend(8000)·sia-frontend(5173) Up. 컨테이너에 실
OPENAI_API_KEY 존재 → **비-guardrail 라이브까지 완전 검증됨**.

### (c) guardrail — "빚내서 몰빵할까" / "반드시 오르는 종목" (curl, 백엔드 8000 + 프록시 5173)
- 헤더: `content-type: text/event-stream; charset=utf-8`, `cache-control: no-cache`,
  **`x-accel-buffering: no`**, **`transfer-encoding: chunked`**(청크 스트리밍 — 버퍼링 없음).
- 프레임: `stage:analyze` → `token(차단문, 면책 포함, 한글 정상)` → `done(popups=[])`.
- **regime/generate 부재 + popups=[]** = 스트리밍이어도 LLM 미호출 결정적 차단, 팝업 없음 실증.
- **Vite 프록시(5173) 경유도 동일** — SSE가 프록시+uvicorn 통해 버퍼링 없이 흐름 확인.

### (a) 삼성전자 — "삼성전자 어때" (실 gpt-5.4 tool 답변)
- 이벤트 순서 실제 재현: `analyze → regime → generate → popups → summarize → token(타이핑)… → done`.
- **popups(실 LLM tool_call)**: `show_stock_report{ticker:"005930", stock_name:"삼성전자", focus:"both"}`.
  ticker "005930" → routePopup valid 게이트 통과 → stock_report 모달. narration 토큰 한 글자씩 타이핑
  (`삼→성→전자→(→005→930→)→ 보고`). done의 popups = popups 이벤트와 동일.

### (b) 매크로 — "지금 시장 어때" (실 gpt-5.4)
- `analyze → regime → generate → popups → summarize → done`.
- popups: `show_macro_dashboard{highlight:"regime"}` → macro_dashboard 모달.

### 라이브 popups name 계약 실증
실 LLM이 생성한 tool name이 프론트 POPUP_KIND 3종(show_stock_report/show_macro_dashboard/
show_watchlist)과 **정확히 일치** — 계약 밖 name·주입성 name 0. 경계면 #3 라이브 확정.

### 브라우저 시각 확인 (미실행 — 확장 미연결)
claude-in-chrome 확장 미연결로 UI 시각 캡처(체크리스트 렌더·커서 애니메이션)는 미실행. 단 SSE
이벤트·popups·타이핑 토큰을 curl 라이브로 실증했고, 프론트 렌더(ChatStages/커서/모달)는 vitest
60 passed로 계약 고정 → 시각 미캡처는 배포 비차단.

---

## 최종 판정: 실패 0 / 안전위반 0 / **배포 가능(GO)**

SSE 스트리밍(#12 chat_stream · #13 SSE 라우트 · #14 sseChat.js · #15 프론트통합) 전 사이클 통과.
- **경계면**: 이벤트 계약 {stage/token/popups/done} ↔ 프론트 핸들러 1:1(양쪽 테스트+실앱 교차). stage
  enum SSOT(chatStages.js=백엔드=sseChat). done popups→기존 routePopups 재사용(경계면 #2·#3 무변경).
- **안전**: guardrail 스트리밍 경로 LLM 미호출(유닛 client.calls==[] + 실앱 프레임 실증) + live_judgement
  미실행(mock 0회 + 실코드 0회). 팝업 tool_calls만·환각차단·시세 무캐시(SSE 실데이터 추출 0). CHAT_MODEL
  단일. 면책 고지 프롬프트+UI 양쪽. 하드코딩 hex/판정숫자 0.
- **회귀**: 백엔드 281 passed(기존 270 + SSE 11, 논스트림 chat()·/api/chat 불변) · 프론트 60 passed
  (기존 40 무손상). 기존 논스트림은 폴백으로 병행 유지.
- **Docker 라이브 e2e**: 삼성전자→stock_report / 시장→macro_dashboard / 몰빵→즉시차단(팝업 0) 3종
  실 gpt-5.4로 실증. SSE 청크 스트리밍(transfer-encoding:chunked, X-Accel-Buffering:no) 프록시 경유 확인.
- **안전 최종 grep 종합**: 주문 API 0 · API 키 하드코딩 0 · CHAT_MODEL="gpt-5.4" 단일 · 프론트 chat hex 0 ·
  초록/황색 0 · SSE 경로 시세 추출 0.

### 잔여(배포 비차단): 브라우저 UI 시각 캡처(확장 미연결 — curl 라이브 + vitest로 계약 고정 대체).
