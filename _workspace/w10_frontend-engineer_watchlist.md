# W10 frontend-engineer — 워치리스트 UI + P2 AI 리포트 UI

담당 Task: #4(watchlistLogic 순수 lib), #5(WatchlistView·팝업·독립패널·능동알림), #9(P2 AI 리포트 UI).
검증: `cd frontend && npm test` → **94개 green**(W09 60 → +34). `npx vite build` clean(56 modules).
디자인: `ui-design-system` 선독. 색은 theme.css 토큰(`var(--c-*)`)만 — 신규 파일 하드코딩 hex 0, 초록·황색 0, 차트토큰 유출 0.

---

## TDD 기록 (테스트 목록 → 구현 순서)

### Task #4 — `src/lib/watchlistLogic.js` (순수, vitest 29개)
Red 먼저(`watchlistLogic.test.js`) → 실패 확인(모듈 없음 / detectTargetAlerts 미정의) → Green.
스펙 근거별 테스트:
- **SORT_KEYS == chat/tools.py show_watchlist enum**(SSOT): `['registered','change_rate','near_target']` 고정 + 각 라벨 존재.
- **distanceToTarget** = `(current-target)/target*100`; target null/0/음수·현재가 결측 → null(0나눗셈·부호역전 방지). 백엔드 `_distance_to_target` 동일.
- **classifyTargetStatus**(매수 진입 관점 — 백엔드 `_target_status` 복제): `reached`(current≤target)/`near`(current≤target*(1+thr%))/`far`/`none`. thr=3.0 경계 포함 검증. ← **초기에 sell 관점으로 잘못 작성했다가 백엔드 service.py 확인 후 buy 관점으로 정정**(필드/의미 추측 금지 원칙).
- **sortItems**(재조회 없이 프론트 재배열, 원본 불변): registered=added_at asc / change_rate=등락률 desc / near_target=distance asc(더 하락=강한 매수신호 먼저)·target없음(dist null) 후순위. 미지 sort_by→registered 폴백, 비배열→[].
- **entrySignalLabel**(진입신호 배지 문구·톤): entry_blocked→"신규 진입 억제"(muted) / per_over·pbr_over→"밸류에이션 부담"(muted) / entry_allowed→"진입 검토 가능"(**emph 주황**) / null→"진입 판정 불가"(muted). **빨강 미사용**(억제는 위험이 아님).
- **detectTargetAlerts**(능동 알림 전이): 이전관측(prevMap {ticker:status}) 대비 **far→near/reached** + **near→reached 승격**만 발화. 유지·악화·none·신규관측(초기 스팸 방지)·prevMap null(초기 로드)→[].

### Task #9 — `src/lib/reportFormat.js` (순수, vitest 5개)
- **opinionTone**: 종합의견 `긍정적`→up(파랑)/`중립`→muted(회색)/`신중`→emph(주황). 미지값(매수 등 스키마 배제 라벨)·결측→muted 방어.
- **OPINION_LABELS**: 긍정적·중립·신중 3종만(Pydantic Literal 일치).

컴포넌트 렌더 테스트는 기존 관례상 없음(@testing-library 미설치) — 로직을 lib 순수함수로 추출해 계약을 고정.

---

## 컴포넌트 ↔ 팝업 툴 매핑

| 팝업 툴(llm chat/tools.py) | popupRouter kind | 컴포넌트 | 실데이터 조회 |
|---|---|---|---|
| `show_watchlist` (args.sort_by) | `watchlist` | `PopupWatchlist` → `WatchlistView` | 프론트 직접(`GET /api/watchlist`) |
| `show_stock_report` (args.ticker) | `stock_report` | `PopupStockReport` → `StockReportView`(하단 `AiReportPanel`) | 번들 `GET /api/detail/{t}/bundle` + P2 리포트는 버튼 클릭 시 `POST .../report` |
| `show_macro_dashboard` | `macro_dashboard` | `RegimeGauge` | `GET /api/macro/regime` |

`popupRouter.js`의 `show_watchlist→watchlist` 매핑은 W09에서 이미 확정 — 변경 없음. LLM은 "무엇을 띄울지"(+sort_by enum)만 주고, 시세·진입신호·리포트 서술 숫자는 프론트가 API로 직접 조회(환각 차단).

**WatchlistView는 팝업·독립페이지 공유 단일 컴포넌트:**
- 팝업: `PopupWatchlist`가 `<WatchlistView initialSortBy={args.sort_by}/>`(마운트 1회 조회).
- 독립패널: `App.jsx`가 `<WatchlistView refreshKey onView/>`(60s interval refresh + 목표가 전이 알림).

---

## 사용 API 엔드포인트 (api.js 신규 함수)

워치리스트(W10):
- `fetchWatchlist(sortBy)` → `GET /api/watchlist?sort_by=` — items·regime·partial_failure·sort_by. sort_by는 서버 에코, 실제 정렬은 프론트.
- `addWatchlist({ticker,stockName,reason,targetPrice})` → `POST /api/watchlist`(upsert).
- `removeWatchlist(ticker)` → `DELETE /api/watchlist/{ticker}`.
- `updateWatchlistTarget(ticker,targetPrice)` → `PATCH /api/watchlist/{ticker}`.

P2 AI 리포트:
- `generateStockReport(ticker)` → `POST /api/detail/{ticker}/report` — report(6필드)|null·validation_failed·quant_summary·message·regime_at_creation·created_at.
- `fetchReportHistory(ticker)` → `GET /api/detail/{ticker}/report/history` — history(created_at 내림차순).

user_id는 미전달(백엔드 기본 `"local"` 단일 사용자).

---

## 소비 계약 검증 (data-engineer w10 + llm-engineer w10 명세 대조 — 일치)

- 워치리스트 GET items 필드(current_price/change_rate/per/pbr/distance_to_target/target_status/entry_signal), regime 블록, partial_failure(=`[ticker… | "regime"]` 문자열 리스트) 모두 data-engineer 확정 shape과 일치. `inPartialFailure`는 문자열/객체 둘 다 방어.
- `entry_signal`/`regime` null(시세·판정 실패) 처리: entrySignalLabel(null)→"판정 불가", regime null→국면 배너 fail 경로. 시세 실패 종목만 값 None + partial_failure에 ticker(나머지 정상 렌더).
- `target_status` 4값·distance 공식·near 임계(3%)는 백엔드 `service.py` 로직을 프론트 `classifyTargetStatus`가 그대로 복제(알림 전이의 클라이언트측 근거) → 서버 값과 불일치 없음.
- P2 리포트: report=null+validation_failed 폴백 → "AI 서술 생성 실패" 안내(전체 에러 아님, 정량요약은 화면 상단 유지). 종합의견 Literal 3종 배지 톤 매핑, 면책고지는 백엔드 필수 필드 + 리포트 하단 상시 노출.

---

## 신규/수정 파일

신규: `lib/watchlistLogic.js`(+test), `lib/reportFormat.js`(+test), `components/WatchlistView.jsx`, `components/AiReportPanel.jsx`.
수정: `api.js`(6함수 추가), `App.jsx`(4번째 패널+능동알림+60s refresh), `components/PopupWatchlist.jsx`(플레이스홀더→WatchlistView 래퍼), `components/StockReport.jsx`(관심종목 추가/제거 버튼), `components/StockReportView.jsx`(하단 placeholder→AiReportPanel), `styles.css`(워치리스트·AI리포트 스타일, 토큰만).
`ChatPanel.jsx` PopupBody `watchlist` case는 이미 `PopupWatchlist`로 라우팅 → 변경 불필요(플레이스홀더가 이제 실 컴포넌트).

## 안전 준수
- 매매 주문 API 0(조회·CRUD·서술 생성만). 목표가 알림은 "안내"만(주문 자동실행 0).
- 현재가 캐시 0(WatchlistView가 열릴 때/60s마다 재조회, 정렬만 프론트 재배열이라 무재조회 — 시세는 항상 서버 최신).
- 진입신호는 `single_cap=0`(entry_blocked) 국면에서 배지가 "억제"로 표시되고 "검토 가능"(emph)은 미표시 — 게이트 동작.
- 빨강(--c-danger) 미사용(진입 억제·목표가 상태는 주황/회색). 면책 고지 종목 리포트 하단 상시.
- 브라우저 alert/confirm/prompt 미사용 — 목표가 편집은 인라인 폼, 능동 알림은 배너 + Notification API(권한 최초 1회).
