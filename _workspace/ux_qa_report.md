# QA 리포트 — UX 개편 트랙 (모달 폐기 2컬럼 + 잔고) incremental

> **최종 상태(2026-07-10, HEAD 6d08387): GO 확정 · 백엔드 472 / 프론트 128 green · build clean.**
> 아래 "실패 항목"은 incremental 착수 시점(사이클 3~4)의 발견 기록이며 **전부 사이클 6에서 해소**됨.
> BalancePanel CSS(`grep -c 'balance__'`=27, 손익 --c-up/--c-down)·네트워크 테스트(global.fetch 경계 mock) 현재 통과.
> 리포트를 시간순으로 읽을 때 중간의 "127/1·CSS 0개"는 과거 스냅샷 — 현재 코드베이스와 대조 시 이미 정정됨.

검증 방법론: `invest-qa-checklist`(교차 비교·3중 일관성·안전 grep). Task #15(UX5).
회귀 기준: W10 통합 검증 완료(GO, w10_qa-inspector_report.md) — 백엔드 403·프론트 98.
incremental — 각 모듈 완성 즉시 검증. 의존 UX1(#11)·UX2(#12)·UX3(#13)·UX4(#14).

**중요 컨텍스트**: KisConfig collection 에러 3개(test_balance_route/test_auth/test_client)는
data-engineer-2 UX2(#12, acnt_no 필드 추가) 진행 중 발생 — UX3(llm) 무관. UX3 검증은 chat 서브스위트 격리 실행.
main.py wiring(balance 라우터 include)은 리더(main) 전담 — 통지 후 통합 검증.

---

## 사이클 1 — UX3 show_balance 툴 + build_prompt ⑦ 규칙 (llm-engineer-2) : 통과 / 실패 0

### 안전 (최우선) — 통과
- **주문 API 0**: chat/tools.py·build_prompt.py 히트는 전부 금지 지시문("사라/담아라 쓰지 않는다":49,
  "팔아라/사라 명령형이 아니라":131) — 위반 아님. show_balance는 조회 팝업 지시만(파라미터 없음).
- **리밸런싱 명령형/단정 0**: build_prompt:131 리밸런싱은 **텍스트만**·"팔아라/사라 명령형이 아니라 국면 현금비중·분산
  원칙 참고 설명" — 데이터는 프론트 조회, 판정/조언은 텍스트. 자동주문 0.
- **환각 차단**: show_balance description(tools.py:121-122)·⑦규칙(:130) "실제 예수금·평가액·수익 숫자는 화면이 직접
  조회, 네가 지어내지 않는다" 명시.
- **misfire 가드**: description에 "리밸런싱·분산 조언·단순질문엔 호출하지 않는다"(tools.py:119).
- **면책 불변**: ⑥블록(:123) "참고용·면허 자문 아님" 유지.

### 계약·경계면 (생산자 측 확정)
- **TOOLS 5종**: show_macro_dashboard·show_stock_report·show_watchlist·manage_watchlist·show_balance
  (W09 3종 → manage_watchlist·show_balance 추가). show_balance parameters={} (파라미터 없음, 단일 계좌).
- **경계면 #3 (show_balance ↔ popupRouter kind) — 소비처 UX4 미착지**: popupRouter.js POPUP_KIND(:12-17)에
  show_balance 매핑 **아직 없음**(4종만). RightPanel.jsx:51 NOTE "case 'balance'→BalancePanel은 UX4 배선" 과 일관.
  → **UX3 실패 아님**(생산자 계약 확정). UX4 착지 시 popupRouter에 `show_balance:'balance'` 추가 + BalancePanel 배선 필요.

### TDD (test-first 증거)
- test_tools.py: test_popup_tool_names(5종·show_balance 포함:38), test_show_balance_has_no_parameters(:81),
  test_show_balance_description_states_when_to_call_and_not(:92, "호출하지 않는다" 가드:96).
- test_build_prompt.py: test_prompt_has_show_balance_rule_in_popup_block(:142), test_prompt_says_rebalance_advice_is_text_only(:149).
- chat 서브스위트 **104 passed** green(격리 실행 — KisConfig 에러 무관).

---

## 미검증 (대상 코드 미착지·진행중)
- **UX1(#11)** 2컬럼 레이아웃 + RightPanel(모달 폐기) — 진행중. Modal 제거 잔재·popupQueue 참조·RightPanel 5종 스위치 검증 대기.
- **UX2(#12)** /api/balance + config 계정 — 진행중(KisConfig collection 에러 진행 신호). balance 어댑터 no-cache·반환 shape 검증 대기.
- **UX4(#14)** BalancePanel + popupRouter 'balance' 배선 — pending. 경계면 #3 소비처·/api/balance shape↔BalancePanel 검증 대기.
- **main.py wiring**(balance 라우터 include) — 리더 전담. 통지 후 통합 앱 검증.

## 현재까지: 통과 1사이클(UX3) / 실패 0 / 안전위반 0

---

# ── qa-inspector-2 인계 후 최종 통합 검증 (2026-07-10, 리더 직접 가동) ──

리더 직접 가동 지시(이름 겹침 오배달 우회). UX1·UX2·UX3 착지 + 리더 wiring 완료 시점.
회귀 기준 갱신: 백엔드 403→**472** · 프론트 98→128(목표). 사이클 1(UX3) 검증은 위와 일치 — 보존.

## 사이클 2 — UX2 잔고 백엔드 (data-engineer-2) : 통과 / 실패 0

### 안전 — 통과
- **조회 전용**: api/balance.py GET만(:49). test_balance_route.py:157 "POST/DELETE/PATCH=405" 능동 방어. 주문 어휘 0.
- **현재가 무캐시**: api/balance.py:17 "현재가 포함 → 캐시 저장 없음". inquire_balance cache 인자 없음(어댑터+CLAUDE.md 양쪽).
- **graceful 실패**: KIS 예외 삼키지 않고(except pass 아님) warning 로깅 + partial_failure=['balance'](:56-60). 항상 200.
- **계정 SSOT**: infra.config.kis_account()(:52) env 로드만. `_optional` 항상 문자열 → cano.split 안전(빈CANO graceful). 하드코딩 0.

### 경계면 #1 (생산자↔소비자 양쪽 동시 읽기 정합)
- normalize_balance(normalize.py:54) 반환 == 계약 정확 일치: holdings 8필드/summary 6필드 == BalancePanel 소비(요약카드 5+표 6열) == test_balance_route BALANCE/HOLDING/SUMMARY_KEYS.

### TDD — 통과
- test_balance_route.py: 경계(client.get)만 stub, normalize_balance 실코드 통과(모킹 남용 0). 손익 양수(+25000)/음수(-25000) 정규화, graceful, 안전405, 계정 params 전달. test-first docstring "Red→Green".
- **test_config.py 격리 버그 해소 확인**(data-engineer-2 지적): 파일 단일(중복 사본 0). importlib.reload 실코드 0(docstring "쓰면 안 되는 이유" 설명뿐). clean_account_env fixture(delenv 후 setenv)로 결정적 격리. UX2 서브스위트 13 passed(config 7+route 6).
- **.env.example**: KIS_ACNT_NO·KIS_ACNT_PRDT_CD_STK 키만 추가(값 플레이스홀더 `<...>`, 시크릿 노출 0).

## 사이클 3 — UX1 레이아웃·모달 폐기 (frontend-engineer-2) : 통과 / 실패 0

- **모달 제거 회귀 완전**: Modal import·popupQueue·activePopup·closePopup·.modal CSS 전부 grep 0(테스트 포함). Modal.jsx 파일 삭제.
- **ChatPanel 전환**: finishStream→routePopups(popups)[0]→onShowPanel(우측 인라인). 과거팝업 재열기 칩(onOpenPopup)도 동일 경로.
- **App.jsx**: 2컬럼(.app__main), rightPanelSpec 리프팅(랜딩 LANDING_SPEC), 앱레벨 fetchWatchlist+detectTargetAlerts 60s 폴링 이관(패널 무관 능동알림).
- **RightPanel**: 퀵버튼 3+종목검색, RightPanelBody 5종 case(stock_report/macro_dashboard/watchlist/manage_watchlist/balance), 종목검색 인라인폼(prompt 금지·ticker.js SSOT). right-panel CSS 15규칙 완비.

## 사이클 4 — 경계면 최종 (잔고 체인 전 구간) : 통과 / 실패 0

```
show_balance(tools.py:115 무파라미터) → POPUP_KIND.show_balance='balance'(popupRouter.js:17)
  → RightPanelBody case 'balance'(RightPanel.jsx:52)→<BalancePanel/> → fetchBalance(api.js:165)
  → GET /api/balance(api/balance.py:49) → normalize_balance shape == 계약 정확 일치
```
- 퀵버튼 '잔고'(RightPanel.jsx:28)→{kind:'balance'} 동일 case. 챗봇·퀵버튼 양경로 동일 컴포넌트.
- 팝업 kind 5종 == RightPanelBody 5 case, 죽은 분기 0. popupRouter.test 5종·RightPanel.test 13 passed.
- partial_failure=['balance'] 문자열 계약 양쪽 일치(balance 라우트 ↔ BalancePanel balanceFailed:115).

## 사이클 5 — 회귀·안전 종합

- **백엔드 uv run pytest → 472 passed / 10 deselected(live)**. 리더 통지치 정확. 무회귀.
- **프론트 npm test → 127 passed / 1 failed**(아래 실패2). 나머지 green.
- **/api/balance 통합 앱 등록**: main.py:76-78 import+include, GET 200 실증(리더 wiring OK).
  (r.path 필터 빈 결과 = _IncludedRouter 래퍼, 이전 사이클10과 동일 검사방식 이슈. openapi/실호출 재확인.)
- **안전 grep 종합**: 주문 API 실질0(조회전용 명시+405테스트+주문키없음테스트) · 현재가캐시0 · 명령형/단정0(금지지시 인용만) · API키하드코딩0 · 면책 상시(BalancePanel 3경로+기존4곳).

---

## 사이클 6 — UX4 프론트 2건 수정 재검증 (frontend-engineer-2) : 통과 / 실패 0

착수 시 발견한 2건이 frontend-engineer-2에 의해 근본 해결됨. 재검증 통과.

### (해소) BalancePanel 손익색·전체 CSS
- styles.css에 `.balance*` **27 규칙 착지**. 손익 방향색: `.balance__pnl.up`→`var(--c-up)`(파랑, :1923)·`.balance__pnl.down`→`var(--c-down)`(회색, :1926)·기본→`var(--c-text-secondary)`. **빨강(danger)·초록·황색·hex 오용 0**(계획 요구 "손익 파랑/회색" 충족).

### (해소) BalancePanel 네트워크오류 테스트 — mock 경계를 fetch로 하향(근본 해법)
- 이전: `vi.mock('../api.js')`로 fetchBalance 직접 reject → 미리 만든 rejected promise가 vitest4 오탐(내가 우회안 5개 실험, 타이밍 조작으론 전부 실패 확인).
- 수정: `vi.stubGlobal('fetch', ...)`로 **HTTP 경계만 mock**. `mockFetchHttpError(500)`이 `{ok:false,status}`를 정상 resolve → **fetchBalance(api.js) 실코드가 `if(!res.ok) throw`를 스스로 실행** → 컴포넌트 catch로 자연 전파. rejected promise 미리 생성 안 됨 → 오탐 원천 제거.
- 부수 이점: fetchBalance(api.js) 실코드가 실제 실행됨 → 모킹 남용 감소, tdd-workflow "경계만 mock" 원칙에 오히려 더 부합(커버리지 향상).

---

## 최종 회귀·안전 종합 (전 항목 그린)

- **백엔드 uv run pytest → 472 passed / 10 deselected(live)**. 리더 통지치 정확. 무회귀.
- **프론트 npm test → 128 passed / 13 files**. 목표 121 초과. 무회귀.
- **프론트 vite build → clean**(0 error, dist 생성).
- **안전 grep 최종(변경 후 재확인)**: 주문 API 실질0(조회전용 명시+405테스트+주문키없음테스트) · 현재가캐시0(balance no-cache) · 명령형/단정0(금지지시 인용만) · API키하드코딩0 · 모달잔재0 · 프론트 신규CSS danger/초록/황색/hex 0 · 면책 상시(BalancePanel 3경로+기존4곳).
- **경계면 전구간 정합**: show_balance(tools.py 5종)→POPUP_KIND.show_balance='balance'→RightPanelBody case 'balance'→BalancePanel→fetchBalance→/api/balance→normalize_balance(holdings 8필드/summary 6필드 계약 정확일치). 퀵버튼 '잔고' 동일 case. 팝업 kind 5종==5 case, 죽은분기 0.
- **모달 폐기 완전**: Modal import·popupQueue·activePopup·closePopup·.modal CSS 전부 0. Modal.jsx 삭제.

## 미검증 (배포 비차단)
- 라이브 e2e(-m live, KIS 키): 실 계좌 balance holdings/summary enrich. 유닛은 fixture로 계약 고정(계획대로).
  ※ 통합 앱 balance 실호출은 실 KIS 조회TR을 탐(조회전용·안전위반 아님) — 통합검증은 monkeypatch 사용.
- 브라우저 수동 통합(랜딩=관심종목·퀵버튼 전환·챗 구동 우측패널·모달 미출현): vitest 128 + build clean으로 계약 대체.

## qa-inspector-2 최종 판정: **UX 개편 통합 검증 완료 · 배포 가능(GO)**
안전위반 0 · 백엔드 472 / 프론트 128 무회귀 · build clean · 경계면 전구간 정합 · 모달 폐기 완전 · 손익 팔레트(파랑/회색·빨강 금지) 충족.
(통과: UX1 모달폐기·2컬럼 / UX2 잔고백엔드 / UX3 show_balance툴 / UX4 BalancePanel·배선 + 리더 wiring)
