# QA 리포트 — WEEK 10 워치리스트 + P2 리포트 (incremental)

검증 방법론: `invest-qa-checklist`(교차 비교·3중 일관성·안전 grep). 승인 계획:
`week-10-delegated-wigderson.md`. 회귀 기준: W09(w09_qa-inspector_report.md·_sse.md = GO).
incremental — 각 모듈 완성 즉시 검증. **라우터 wiring(api/main.py include + CORS DELETE/PATCH)은
리더(main) 전담** — 백엔드 에이전트가 main.py 미변경은 정상, "라우터 미등록"을 실패로 오판 금지.

## 착수 전 안전 베이스라인 (2026-07-09, 클린)
- 주문 API grep(`order_cash|order_rvsecncl|buy_order|sell_order|주문`, .venv 제외): 실질 0.
  히트 3건 전부 "조회 전용/주문 안 함" 명시 주석·프롬프트(collectors/client.py:5, errors.py:8, build_prompt.py:82).
- API 키 하드코딩 grep: 0.
- 모델명 grep: CHAT_MODEL="gpt-5.4"(chat/tools.py:16) 단일 정의 + 주석/명세/테스트 assert만. 산재 0, gpt-4o 잔재 0.
- watchlist 서브스위트 65 passed / chat 서브스위트 88 passed / 프론트 vitest 80 passed 그린.
- 전체 pytest 380/389 collect(9 라이브 deselect). test_watchlist_route·test_report_route는
  라우트 미구현으로 collection error = **정상 TDD Red**(라우트 착지 시 해소 예정).

---

## 사이클 1 — T1 constants·models·store (data-engineer) : 통과 / 실패 0

- **SORT_KEYS 3중 일관성(프론트·LLM 축 확정)**: constants.py:11 `("registered","change_rate","near_target")`
  == chat/tools.py:79 show_watchlist enum == watchlistLogic.js:9 → 3층 일치.
  test_sort_keys_consistency 로 백엔드↔tools.py 강제.
- **ticker 정규식 SSOT**: models.py:14 `^[0-9A-Za-z]{6}$` = frontend ticker.js 동일. target_price ge=0(음수 거부).
- **store durable(캐시 아님)**: 원자적 write(temp+os.replace, store.py:104-110)+threading.Lock,
  upsert added_at 보존(:45-49), (user_id,ticker) 격리. 시세 필드 저장 0(캐시 3원칙 무관).
- test_models·test_store·test_sort_keys_consistency green.

## 사이클 2 — T2 service·진입신호 (quant-engineer) : 통과 / 실패 0

- **regime-agnostic(핵심 회귀)**: service.py:139 `entry_blocked = params.get("per_max") is None`,
  regime_gate:314 동일. single_cap 소비만(:70) — 국면명 하드코딩 0. 과열만 per_max=None(REGIME_PARAMS).
- **재사용 자산 재정의 0**: stock.summary.regime_gate·macro REGIME_PARAMS import만, 임계값 재정의 없음.
- **경계 케이스 커버(test_service.py, mock=inquire_price 경계만)**: 과열(single_cap=0→entry_blocked)·
  수축(single_cap=5→미차단) 둘 다 / target_status 4상태(reached·near·far·none) / 부분실패(값 None +
  partial_failure에 ticker, 저장필드 유지) / judgement=None(entry_signal None + partial_failure "regime").
- **시세 무캐시**: inquire_price 병렬 호출(캐시 미경유, 원칙1). watchlist store와 시세 경로 분리.
- watchlist 서브스위트 65 passed green. 모킹 남용·가짜 테스트 0(내부 로직 실코드 실행).

## 사이클 3 — T6 build_prompt ⑤블록 진입신호 지침 (llm-engineer) : 통과 / 실패 0 (3중 일관성)

- **하드코딩 숫자 0**: ⑤블록(build_prompt.py:107-114) single_cap>0·per_max·pbr_max 이름 참조만.
  실제 값은 ④블록 _format_params(:45-54)가 REGIME_PARAMS에서 주입 → SSOT 파생. ⑤블록에 판정 임계값(15/20/1.5/2.0) 리터럴 0.
- **regime-agnostic**: single_cap=0 국면 → "신규 진입을 제안하지 않는다"(:111), 국면명 하드코딩 0.
- **명령형/단정 표현 0**: "사라/지금 담아라 쓰지 마라"(:113) 금지지시 인용만. "검토 가능=매수 권유 아님"(:113).
- chat 서브스위트 88 passed green.

## 사이클 4 — T7 report_schema (llm-engineer, P2) : 통과 / 실패 0 (안전 스키마 강제)

- **리스크요인 min_length=1**(report_schema.py:36) — 장밋빛 리포트(리스크 0) 방지, 검증 실패로 강제.
- **면책고지 필수 str**(:39) — 누락 시 ValidationError.
- **종합의견 Literal["긍정적","중립","신중"]**(:32) — "매수/매도" 명령형 라벨 타입에서 원천 배제.
  OPINION_VALUES(:22) 상수 = 프론트 배지 매핑 SSOT 예약.
- **투자포인트·리스크요인 max_length=3** — 과대 나열 방지.
- test_report_schema green(리스크0 거부·투자포인트4 거부·종합의견 오값 거부·면책 누락 거부).

## 사이클 5 — T8 report·report_store (llm-engineer, P2) : 통과 / 실패 0 (라우트는 미검증)

- **CHAT_MODEL 단일**(report.py:27 import), API키 환경변수(:38-40 openai_api_key) 하드코딩 0.
- **폴백 안전**: 검증 실패 → 1회 재요청 → 폴백(validation_failed=True, report=None, 정량요약 보존)(:124-143).
  OpenAI 예외도 흡수(:127) 크래시 0. §5.1 부분실패 보존.
- **LLM 설명만**: 프롬프트가 "재판정·새 숫자 금지, 컨텍스트 밖 숫자 금지, 단정 금지, 면책 필수"(:83-87).
  build_criteria_text() 재사용(:68) → 기준표 3중 일관성 상속.
- **report_store**: append-only (ticker,created_at) 히스토리, 원자적 write+Lock(watchlist store 동일 패턴).
- test_report_generate(FakeOpenAI 정상→통과/불량→재시도→폴백)·test_report_store green.

## 사이클 6 — T4 watchlistLogic.js (frontend-engineer) : 통과 / 실패 0 (경계면 백엔드 대조)

- **classifyTargetStatus(:35-41) == 백엔드 _target_status(service.py:38-52)**: reached/near/far/none 로직 동일.
  능동 알림 전이(far→near/reached) 판정의 클라이언트 근거 — 계약 일치 필수인데 정확 복제.
- **distanceToTarget(:23-27) == _distance_to_target**: (current-target)/target*100, 결측/0→null. 음수 target까지 방어.
- **SORT_KEYS(:9) 3중 일치** + entrySignalLabel 계약(entry_blocked/per_over/pbr_over/single_cap/entry_allowed/note)
  = service.py _entry_signal 반환과 대응.
- **디자인**: tone emph(주황)/muted(회색)만, 빨강 미사용("진입 억제=위험 아님"). hex/초록/황색 0.
- 프론트 vitest 80 passed(기존 60 + watchlistLogic 20) green.

---

## 사이클 7 — T3 api/watchlist.py CRUD 라우트 (data-engineer) : 통과 / 실패 0 (경계면 #1)

- **라우트 계약**: GET {items,regime,sort_by,partial_failure} / POST {ok,item} / DELETE {ok} / PATCH {ok,item}.
  ticker 불량=400(:122-123, 저장 안 함), target 음수=422(Pydantic ge=0), PATCH 미등록=404, DELETE idempotent.
- **순환 import 없음**: api.detail만 재사용, api.main 미참조(grep 확인). 얇은 라우트(client·judgement·store→service).
- **regime degraded**: judgement 실패→None(:112-113)→service가 regime=None + partial_failure "regime"(항상 200, 시세 정상).
- **경계면 #1 (GET shape ↔ WatchlistView 소비) 양쪽 동시 읽기 정합**: _enrich_item 반환 필드 =
  WatchlistView가 읽는 필드(current_price/change_rate/per/pbr/entry_signal/distance_to_target/target_status) 정확 대응.
  partial_failure "regime"(judgement) vs ticker(시세) 구분을 프론트 inPartialFailure(...'regime')+filter로 정확 분리 소비.
- test_watchlist_route.py: 경계만 monkeypatch, 라우트 로직 실코드. GET empty/enriched/sort echo/폴백/degraded,
  POST 추가/이름해석/불량400/upsert, DELETE, PATCH 404/음수422, user_id 격리 전부. 주문/키/모델 하드코딩 0.

## 사이클 8 — T8 api/report.py 라우트 (llm-engineer, P2) : 통과 / 실패 0

- POST /api/detail/{ticker}/report — bundle→judgement→generate_stock_report→**검증 통과분만 히스토리 저장**(:57,
  폴백은 durable 히스토리에 미저장)→반환. 폴백(validation_failed)도 200(정량요약 보존). regime 실패→regime_at_creation=None.
- GET history — created_at 내림차순. 순환 import 없음(api.detail만), 주문/키/모델 하드코딩 0.
- test_report_route.py 경계 monkeypatch, POST 생성·저장/created_at/폴백 미저장/GET history 검증.

## 사이클 9 — T5 완성분 WatchlistView·PopupWatchlist·api.js (frontend-engineer) : 통과 / 실패 0 (경계면 #3)

- **경계면 #3 (popupRouter)**: show_watchlist→'watchlist'(popupRouter.js:15)→ChatPanel case 'watchlist'→
  PopupWatchlist→WatchlistView(initialSortBy=args.sort_by). 챗봇 팝업 실데이터 프론트 직접 조회 경로 완성.
- **디자인/안전**: hex/초록/황색 0, alert/confirm/prompt 0(인라인 편집 TargetCell), --c-danger 미사용
  (진입억제/목표가=emph 주황/muted 회색만, 빨강 금지 준수). null 방어, 정렬 재조회 없이 sortItems, 무한스피너 방지.
- **api.js 4함수** 계약 = api/watchlist.py 정확 일치. vitest 80 passed.

---

## 회귀 스냅샷 (라우트 착지 후)
- **백엔드 pytest 401 passed / 9 deselected(live)** — W09 베이스라인 281 → +120(W10 신규). collection error 해소, 회귀 0. 목표 300+ 초과.
- **프론트 vitest 80 passed / 7 files** — W09 60 → +20(watchlistLogic). 회귀 0. 목표 70+ 초과.

## 미검증 (진행중 — 정상, 배포 비차단)
- **T5 잔여**: App.jsx 4번째 독립 패널 + 능동 알림 배너(주황)·브라우저 Notification(far→near/reached 전이) +
  60s refreshKey interval + StockReport "관심종목 추가/제거" 버튼. 현재 src/App.jsx는 W09 상태(Macro+Stock+Chat).
  WatchlistView가 onView/refreshKey props 이미 수용 → App 연결만 남음.
- **T9 (P2 프론트)**: AI 리포트 생성 버튼·구조화 렌더(종합의견 배지·리스크요인·면책 상시)·히스토리. reportLogic.js는 착지(테스트 green).
  착지 시 report route POST/GET shape ↔ 프론트 소비 경계면 교차 검증.
- **api/main.py 라우터 wiring**(watchlist·report include + CORS DELETE/PATCH) — 리더(main) 전담. wiring 통지 후 통합 앱(api.main.app)으로 전체 검증.

## 사이클 10 — 통합 wiring 검증 (리더 main.py wiring 완료 후) : 통과 / 실패 0

- **통합 앱 라우트 등록(OpenAPI)**: /api/watchlist [GET,POST], /api/watchlist/{ticker} [DELETE,PATCH],
  /api/detail/{ticker}/report [POST], /report/history [GET] — 리더 통지와 정확 일치.
  (초기 덤프가 빈 결과였던 건 include된 라우터가 _IncludedRouter 래퍼 타입이라 getattr(path) 필터 미포착 — 검사방식 문제, 버그 아님. openapi() 스펙으로 재확인.)
- **CORS allow_methods=["GET","POST","DELETE","PATCH"]**(main.py:36). TestClient preflight DELETE → 200, allow-methods에 DELETE/PATCH 포함 실증.
- **통합 앱 TestClient CRUD 스모크**: GET/POST/PATCH/DELETE 전 경로 200, 반환 shape {items,regime,partial_failure,sort_by} 정확, entry_signal.entry_allowed 파생 정상.
- **regime_gate single_cap=0 게이트 회귀**: 과열 single_cap=0/per_max=None → entry_blocked=True(싼 종목 per=3/pbr=0.5도 차단, 안전 반전 없음).
  수축=5/회복=4/확장=3 미차단. 국면명 하드코딩 0(REGIME_PARAMS 소비만).

## 사이클 11 — T5 완성(App 독립패널·능동알림) : 통과 / 실패 0

- **능동 알림 안전**: App.jsx onWatchlistView → detectTargetAlerts(items, prevStatusRef). 마운트 첫 관측(prev=null)·신규 관측(prev undefined) 억제(무더기 발화 방지).
  **far/none→near/reached 개선 전이만 알림**, near→reached 승격 인정, near→near·reached→near(이탈) 무시(watchlistLogic.js detectTargetAlerts). 매수관점 정확.
- **"안내"만**: alertMessage "관심종목을 확인해 보세요" — 주문 자동실행 0. 배너=banner--emph(주황), 빨강 아님(손실경고 아님).
- **Notification 권한 1회 요청**(notifiedRef), denied→배너만. 60s interval + 언마운트 clear.
- **StockReport 관심종목 담기/빼기** 버튼(addWatchlist/removeWatchlist, ticker=번들 기준).

## 사이클 12 — T9 완성(AiReportPanel 리포트 UI) : 통과 / 실패 0 (경계면 report shape↔렌더)

- **경계면 (report POST/GET shape ↔ AiReportPanel) 양쪽 동시 읽기 정합**: api/report.py 반환
  {ticker,report:{6필드},validation_failed,message,regime_at_creation,created_at} = AiReportPanel 소비(:44-50).
  StructuredReport가 종합의견/요약/투자포인트/리스크요인/국면정합성/면책고지 = Pydantic StockReport 6필드 정확 렌더.
- **안전**: validation_failed→report=null→"AI 서술 생성 실패" 안내(정량요약 상단 존재, 전체 에러 아님).
  면책고지 하단 상시(report.면책고지) + StockReportView 자체 DISCLAIMER 코드 고정 = 이중. 리스크요인 항상 렌더(min1 대응).
- **팔레트**: opinionTone 긍정적=up(파랑)/중립=muted(회색)/신중=emph(주황), 미지값·명령형("매수")→muted 방어(reportFormat.test 실증). 빨강 미사용.
- AiReportPanel이 StockReportView:241에 마운트(팝업·독립 공유). hex/초록/황색/danger 오용 0, alert/confirm/prompt 0.

---

## 최종 회귀·안전 종합
- **백엔드 pytest 403 passed / 9 deselected(live)** — W09 281 → +122. 무회귀. 목표 300+ 초과.
- **프론트 vitest 94 passed / 8 files** — W09 60 → +34. 무회귀. 목표 70+ 초과. build 0 error.
- **안전 grep 종합(전체, .venv 제외)**: 주문 API 실질 0, API키 하드코딩 0, CHAT_MODEL="gpt-5.4" 단일,
  현재가 캐시 0(watchlist store=durable 상태, 시세는 inquire_price 캐시 미경유), 명령형/단정 0(금지지시 인용만),
  프론트 초록/황색 0(차트 예외 토큰 제외), 신규 컴포넌트·styles hex 0.
- **3중 일관성**: SORT_KEYS 3층 일치, REGIME_PARAMS 단일 출처(재정의 0), Pydantic 리스크 min1·면책 필수 실동작.
- **경계면 교차(양쪽 동시 읽기)**: #1 GET shape↔WatchlistView, #3 popupRouter watchlist, report shape↔AiReportPanel — 전부 정합.

## 사이클 13 — 최종 전면 검증 (리더 지시, 모든 구현 착지 후) : 통과 / 실패 0

리더 지시 4항목 전면 재검증. 완성된 통합 앱(api.main.app) + 완성 프론트로 실증.

### T3 후속 — WATCHLIST_MAX_ITEMS 상한 게이트(409) : 통과
- api/watchlist.py:131 `existing is None and len(store.list_items(uid)) >= WATCHLIST_MAX_ITEMS` → **신규 종목만 상한 검사**,
  upsert(기존 ticker)는 개수 안 늘어나 허용. 거부 시 store.put 전 HTTPException → 미저장.
- **통합 앱 실증**: 상한 2에서 1·2번 200, 3번 신규→409+미저장, 기존 upsert→200(개수 2 유지). test 2건(거부·upsert) green.

### 전체 스위트 직접 실행 (리더 기대치 일치)
- **백엔드 `uv run pytest -q` → 403 passed / 9 deselected(live)**. 무회귀.
- **프론트 `npm test` → 94 passed / 8 files**. 무회귀.

### 경계면 재검증(프론트 완성) — 실증
- **classifyTargetStatus(프론트) ↔ _target_status(백엔드) 8케이스 실증 일치**: reached(≤target)·near(≤target*1.03)·far·none.
  경계값 82400=near/82500=far(thr=3%) 정확. 매수관점 semantics 동일.
- **report POST validation_failed 폴백 통합 앱 실증**: POST 200 + report=null + validation_failed=True + quant_summary 보존
  + **폴백은 히스토리 미저장(GET history len=0)**. AiReportPanel이 이 shape를 소비(:44-50, StructuredReport 6필드).
- **409 상한** 통합 앱 실증(위). watchlist GET/POST/DELETE/PATCH shape ↔ WatchlistView/App/StockReport 소비 정합(사이클 7·9·11).

### 안전 최종 (grep + 실동작)
- 주문 API 0, API키 하드코딩 0(전체 grep). 프론트 빨강(--c-danger) 오용 0(진입억제/목표가/종합의견은 emph 주황·muted 회색만).
- **면책 고지 3곳 상시**: ChatPanel·StockReportView·AiReportPanel(grep 확인). + report.면책고지 스키마 필수.
- single_cap=0 게이트 회귀(과열=entry_blocked, 국면명 하드코딩 0) — 사이클 10 실증 유지.
- **Pydantic 안전 실동작 실증**: 리스크0개 거부·면책 누락 거부·종합의견"매수"(명령형) 거부·투자포인트4개 거부.

### 3중 일관성 최종 — 실증
- **SORT_KEYS 3층 실코드 파싱 대조 일치**: constants.py == chat/tools.py show_watchlist enum == watchlistLogic.js.
- **REGIME_PARAMS 재정의 0**: 신규 모듈 전부 macro.engine import만(grep). SSOT 유지.

---

## 사이클 14 — 프론트 409 상한 UX 대응 보강 (frontend-engineer 후속) : 통과 / 실패 0

백엔드 409 상한 게이트에 프론트가 사용자 안내로 대응 — 경계면(백엔드 status ↔ 프론트 문구) 강화.
- api.js addWatchlist: `!res.ok`이면 `err.status = res.status` 실어 throw → 호출부 409 판별 근거.
- watchlistLogic.js addErrorMessage(status): 409="가득 찼습니다(최대 30개)"·400="종목 코드 인식 못함"·422="목표가 0 이상"·default
  = 백엔드 상태코드(409/400/422) 정확 대응. StockReport.jsx가 addWatchlist 실패 시 `setWlErrorMsg(addErrorMessage(e?.status))`.
- **안전**: wl-add-status--err = var(--c-text-secondary)(회색), 빨강·주황 아님(상한 초과는 위험 아닌 단순 안내). 테스트 계약 명시.
- watchlistLogic.test.js 20→33(+13, addErrorMessage·detectTargetAlerts 전이 보강). 프론트 vitest 94→98 순증, build clean.
- 변경 후 프론트 안전 재확인: 빨강/초록/황색/명령형 0.

## 최종 판정: 통과 14사이클 / 실패 0 / 안전위반 0 / **W10 통합 검증 완료 · 배포 가능(GO)**
(완료·검증 통과: T1·T2·T3(+409)·T4·T5·T6·T7·T8·T9 전부 + 통합 wiring + 프론트 409 UX 대응)
현재 스냅샷: 백엔드 403 passed / 9 deselected(live) · 프론트 98 passed / 8 files · build clean.

### 잔여(배포 비차단): 라이브 e2e(-m live, KIS/OPENAI 키 필요) — 실 KIS 워치리스트 enrich·실 gpt-5.4 리포트 생성 스모크. 유닛은 경계 mock으로 계약 고정(계획대로). 브라우저 UI 시각 캡처는 vitest 94 + 빌드로 계약 대체. doc-commit 전 마지막 게이트 통과.
