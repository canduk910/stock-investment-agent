# frontend/ — React + Vite

## 실행
- 백엔드 먼저: `uv run uvicorn api.main:app --port 8000` → 프론트: `npm run dev`.
- **`http://localhost:5173`로 연다** — Vite가 IPv6 localhost에 바인딩하므로 `127.0.0.1:5173`은 안 될 수 있다.
- Vite dev가 `/api`를 `http://127.0.0.1:8000`으로 프록시 → 개발 중 CORS 불필요.

## 디자인 (반드시 준수)
- 팔레트는 **흰색/회색/파랑/남색/검정 + 강조 주황(`--c-emph`) + 위험 빨강 경보(`--c-danger`)**. 초록·황색 금지.
- **가격/손익 방향(사용자 확정, 전 화면)**: **모든 주식 수치 상승·수익 = 빨강(`--c-up`)/하락·손실 = 파랑(`--c-down`)/보합 = 회색(`--c-flat`)** — 한국 관습을 전 화면에 적용(이제 차트만의 예외 아님). 색만으로 구분 금지 → ▲▼─ 글리프 병기.
- **주황=강조**(국면명·현금비중·목표가 상태·진입 검토·알림·확인 CTA), **빨강 경보=위험**(손실경고 배너·VIX 패닉 칩만) — 채움형 배너/칩 + ⚠ 로 상승 빨강과 형태 구분. 두 난색은 역할을 섞지 않고 가격 방향엔 주황·경보빨강 금지.
- 색은 **`src/theme.css` 토큰(`var(--c-*)`)만** 참조. 컴포넌트에 hex 하드코딩 금지. 전체 규칙: `ui-design-system` 스킬.
- **캔들차트(KLineChartPanel)**: 전용 토큰 **`--c-chart-up`(빨강)/`--c-chart-down`(파랑)** 사용 — 값은 `--c-up/--c-down`과 같아졌지만 `lib/theme.js::readChartPalette` 주입 경로 보존을 위해 토큰 분리 유지. 지표선(MA/RSI)·52주/현재가선은 남색·회색으로 캔들과 구분.

## 계약
- `GET /api/macro/indicators` → `{indicators, partial_failure}` 소비. 지표가 `null`이면 "일시 조회 불가" 카드로 표시하고 나머지는 정상 렌더(부분 실패 보존). 지표 키·shape은 백엔드(`api/main.py`)와 일치해야 한다.
- 화면은 단계적으로 성장: 1단계 지표 대시보드 → W07 국면 게이지 → W08 종목 리포트 → W09 챗봇/팝업 → W10 워치리스트·구조화 리포트 → **UX 개편: 좌측 상시 채팅 + 우측 동적 패널(모달 폐기)·잔고 패널(완료)**. 새 화면도 같은 토큰을 조합해 한 제품처럼 보이게.

## UX 레이아웃 — 좌측 채팅 + 우측 동적 패널 (모달 폐기)
- **`App.jsx` = 2컬럼 그리드**(`.app__main`: 좌 `ChatPanel` 상시 / 우 `RightPanel`). 반응형 ~1024px 이하 세로 스택. 상단 세로 스택(상시 지표 그리드)·**모달(`Modal.jsx` 삭제)** 폐기 — 컴포넌트를 우측 패널에 **인라인** 렌더한다.
- **톱바 리브랜딩(Refined Pro)**: DK 모노그램 인라인 SVG(`DkMonogram`, 색은 `var(--c-navy)/--c-emph/--c-white`) + 파랑 워드마크 "디케이 투자에이전트"(`--c-brand`) + **상태 칩**(현재 국면·권장 현금비중·VIX 패닉) — App이 `fetchMacroRegime`를 **자체 조회**(환각 차단)해 그리며, 조회 실패해도 칩만 생략(전체 에러 화면 금지). 목표가 알림 배너는 주황 풀폭(+[관심종목 보기]).
- **우측 패널은 두 경로로 구동**: (a) 챗봇 tool_call(`onShowPanel(routePopups(popups)[0])`), (b) `RightPanel` 상단 **세그먼트 탭**(관심종목·시장 국면·내 잔고 — 활성=네이비 채움) + 우측 **인라인 종목검색**(`TickerSearch`). kind 전환 시 **450ms 스켈레톤**(초기 마운트 제외). 상태는 `App`의 `rightPanelSpec`(`{kind,args,valid}`) 단일 소유, **랜딩=관심종목**(`{kind:'watchlist'}`).
- **종목명 자동완성(항목6 원복)**: `TickerSearch`는 종목명/코드 입력 → `searchStocks(q,8)`(`GET /api/stocks/search`, KIS 마스터·`StockReport.jsx` 패턴) 디바운스(180ms) → `.autocomplete` 드롭다운(name·`{ticker}·{market}`, 키보드 ↑↓·Esc·바깥클릭 닫힘) → 선택 시 `onSubmit(ticker, 종목명)` → `{kind:'stock_report', args:{ticker, stock_name}, valid:true}`(종목명이 패널 제목에 반영). 제출 우선순위: 활성후보→`isValidTicker` 코드직접→첫후보→(후보 없으면)안내만(잘못된 백엔드 조회 방지). 검색 실패는 조용히(코드 직접입력 경로 보존). 백엔드·`.autocomplete*` CSS 재사용(변경 0), `.right-panel__search-box`(relative 앵커)만 신규.
- **`RightPanel.jsx`의 `RightPanelBody` switch = 렌더 SSOT**: `stock_report→PopupStockReport`·`macro_dashboard→RegimeGauge`·`watchlist→PopupWatchlist`·`manage_watchlist→ManageWatchlistConfirm`·**`balance→BalancePanel`**·**`settings→KisSettingsPanel`**. 팝업 컴포넌트는 전부 모달 비종속·자체조회형이라 **재작성 0**으로 인라인 재사용.
- **'설정' 탭(`KisSettingsPanel`)** — 유저별 KIS API 키 등록/상태/삭제. **탭 전용**(챗 `POPUP_KIND` 아님 — popupRouter 무관). 시크릿은 서버로만(응답에 원문 없음), 상태는 마스킹만(`app_key_masked`·`account_masked`·source). 저장=주황 `--c-emph` CTA(서버가 실제 KIS 토큰 발급으로 검증 후 저장, 실패 시 파랑 배너). `api.js` `set/fetch/deleteKisCredentials`. **KIS 데이터 fetch(`fetchBalance`·`fetchStockBundle`·`generateStockReport`·`fetchReportHistory`)는 authFetch로 전환** — 로그인 시 토큰 전송 → 백엔드가 본인 KIS 키 사용(미로그인은 공유 fallback).
- **목표가 능동 알림은 `App` 레벨로 이관**: WatchlistView가 이제 온디맨드(상시 마운트 아님)라, 60s 폴링을 `App`이 직접(`fetchWatchlist`+`detectTargetAlerts`) 수행 → 패널 내용과 **무관하게** 앱레벨 배너+`Notification` 동작.

## 챗봇 (W09)
- **응답은 SSE 스트리밍**(`postChatStream`→`POST /api/chat/stream`)이 기본, `postChat`(논스트림)은 폴백. `lib/sseChat.js`의 `parseSSEBuffer`(순수함수)가 `\n\n` 경계로 이벤트를 재조립한다 — 청크가 경계를 가로질러/여러 이벤트가 한 청크로 오는 경우 방어(TextDecoder `stream:true`). 이벤트 `{type:stage|token|popups|done}`, stage enum은 `lib/chatStages.js`가 백엔드와 **SSOT로 공유**.
- `ChatPanel`은 스트리밍 상태기계: 봇 placeholder를 만들고 `onStage`(진행 체크리스트)·`onToken`(라이브 타이핑)·`onDone`(→`routePopups`→**`onShowPanel`로 우측 패널**) 갱신. 스트림 실패 시 `postChat` 폴백 1회. streaming 중 입력 비활성, 무한 스피너 금지(에러 배너+재시도). (모달·`popupQueue` 폐기 — 팝업은 우측 패널로만.)
- **팝업 실데이터는 LLM 응답이 아니라 프론트가 직접 조회**(환각 차단): `popups[].name`→`lib/popupRouter.js`가 컴포넌트로 라우팅(`show_stock_report`→번들 API, `show_macro_dashboard`→regime API, `show_watchlist`→watchlist API, **`show_balance`→`/api/balance`**). `POPUP_KIND` 5종이 라우팅 SSOT. LLM은 "무엇을 띄울지"만 준다.
- **ticker 유효성은 `lib/ticker.js` 단일 출처**(`/^[0-9A-Za-z]{6}$/`) — 직접입력(StockReport)과 팝업 라우팅이 공유. 불량 코드는 조회 없이 안내로 graceful 처리.
- 챗 신규 UI도 `theme.css` 토큰만(hex/초록/황색 0), 면책 고지 상시 노출.

## 잔고 패널 (UX 개편 · 리디자인)
- **`BalancePanel.jsx`**: `/api/balance` **자체 조회**(환각 차단) → **네이비 히어로 카드**(순자산 큰 값 + 평가손익 pill: 수익=`--c-up-onnavy` 밝은 빨강/손실=`--c-blue-soft` 밝은 파랑) + 보조 카드 4(예수금·매입액·평가액·보유종목) + 보유종목 표. **조회 전용**(주문/매매 없음), 현재가 포함이라 무캐시. `partial_failure:['balance']`(KIS 실패)는 **dashed 카드** "일시 조회 불가"·재시도 graceful, 네트워크/HTTP 오류도 재시도 버튼(무한 스피너 금지). 면책 상시.
- **손익 색 = 글로벌 팔레트(수익=빨강 `--c-up`/손실=파랑 `--c-down`/보합=회색 `--c-flat`)** — WatchlistView 등락률과 동일 규칙(리디자인 반영). 손실은 파랑이며 빨강 경보(`--c-danger`) 금지(경보는 채움 배너/칩 전용). 색만으로 구분 안 하도록 ▲▼─ 글리프 병기.

## 애널리스트 리포트 요약 + "이 리포트로 상담하기" (네이버 연계)
- **`AnalystReportsSection.jsx`**: `StockReportView` 하단 섹션. `GET /api/detail/{ticker}/analyst-reports` **자체 조회**(환각 차단)로 그 종목 리포트 요약 카드 렌더 — 증권사·작성일·목표주가·**투자의견(‘리포트 의견 ·’ 접두로 출처 귀속**, 가격 방향색·주황/빨강 아님 = 에이전트 판정 아님)·핵심요지·리스크·면책·원문 PDF 링크. 빈 상태 + **"네이버 최신 리포트 가져오기"**(`POST /api/reports/fetch` → 재조회). 상담 CTA=**주황 채움**(`--c-emph`).
- **최근 3개 종합요약(항목5)**: 개별 카드 **위**에 `CombinedSummary` 패널 — "종합요약 생성" 버튼(주황 CTA·리포트 ≥1일 때만 표시) → `fetchAnalystReportsSummary(ticker)`(`POST …/analyst-reports/summary`, 온디맨드) → 의견분포 칩(중립)·목표주가범위 칩(네이비)·리포트N개 칩 + **10줄 `<ol>` 종합요약**·면책 렌더. 로딩/생성실패(`validation_failed`)/0개는 안내(무한 스피너 금지). 종합=여러 리포트 인용(판정 아님)·면책. 저장 요약만으로 서버가 종합(프론트 신뢰전송 없음).
- **"이 리포트로 상담하기"**(카드별) → `setReportContext(sessionId, ticker, reportId)`(서버가 store 에서 요약 조회해 세션 컨텍스트 세팅) → 성공 시 `onConsult(broker)` → 좌측 챗 상단 **주황 상담 배너**(`chat__consult`) "○○증권 리포트로 이어서 물어보세요" + **[상담 종료]**(App `endConsult`가 서버 컨텍스트 해제). 이후 후속 질문은 그 리포트 근거로 답(출처 귀속·면책, 백엔드 세션 핀).
- **세션 id 는 `App` 이 단일 소유**(리팩터): 좌측 `ChatPanel`(대화)과 우측 리포트 "상담하기"가 **같은 session_id 를 공유**해야 컨텍스트가 대화에 반영된다 → `App` 이 `useRef`로 생성해 두 패널에 prop 전달. `ChatPanel`은 prop 우선, 미전달 시 자체 생성 폴백(구 테스트 호환). 프롭 경로: `App → RightPanel → RightPanelBody → PopupStockReport → StockReportView → AnalystReportsSection`(sessionId·onConsult).
- `api.js`: `fetchAnalystReports(ticker)`·`fetchNaverReports(limit)`·`setReportContext(sessionId, ticker, reportId)`. 테스트는 jsdom + api.js mock(빈 상태·수집 재조회·상담 콜백·세션 없음 비활성).

## 현재 보는 화면 → 챗 세션 컨텍스트 (P1)
- **`App.jsx`가 `rightPanelSpec` 변경 `useEffect`로 현재 화면을 챗 세션에 핀**한다 — 사용자가 잔고/관심종목/종목상세를 열면 챗봇이 그 데이터를 근거로 대화하게 된다. `setViewContext(sessionId, kind, args)`(`api.js`→`POST /api/chat/context`). **화면 데이터는 보내지 않음** — kind/args만 보내고 서버가 재조회(환각 차단).
- **데이터 kind만 대상** `VIEW_CONTEXT_KINDS={watchlist,balance,stock_report}`(백엔드 `view_context.DATA_BEARING_KINDS`와 SSOT 일치). macro_dashboard·manage_watchlist 등 비데이터/무효 spec은 `kind=null`로 **이전 핀 해제**(스택난 스냅샷 방지). **400ms 디바운스**(빠른 탭전환 KIS 폭주 방지) + **중복 kind+args 스킵**(`useRef` last-key) + **fire-and-forget**(`.catch`). 랜딩(watchlist) 마운트 1회 발화.
- 챗이 화면을 여는 그 턴은 백엔드 P2(툴 결과 스냅샷 되먹임)가 같은 턴 즉답을 담당(프론트 무관). `App.test.jsx`는 `./api.js` mock에 `setViewContext` 포함 필수(effect가 마운트 시 호출).

## 로컬 도커 기동 (대안 실행)
- `docker compose up --build` → `localhost:5173`(프론트)+`:8000`(백엔드). 시크릿은 `.env` 런타임 주입(`env_file`), 소스 핫리로드. Vite 프록시 대상은 `VITE_PROXY_TARGET`로 재정의(도커=`http://backend:8000`). 상세는 루트 `DOCKER.md`.

## 워치리스트 + 구조화 리포트 (W10)
- **`WatchlistView`는 단일 본문 컴포넌트** — `PopupWatchlist`가 래핑, 우측 패널(랜딩 기본)·챗 트리거가 같은 본문을 공유(UX 개편으로 모달→우측 인라인). 실데이터는 프론트가 `/api/watchlist`로 직접 조회(환각 차단). `popupRouter`의 `show_watchlist→watchlist` 계약 유지.
- **리디자인: 테이블→카드 로우**(`.wl__row`) — 종목명·코드/사유 + **스파크라인**(`Sparkline`, watchlist 응답 `spark:number[]|null` SVG, 선색=방향색 `--c-up/--c-down`, 결측 시 생략) + 등락 칩(소프트 배경) + 현재가 + PER/PBR + **목표가 근접 게이지**(`gaugeWidth(distance)`, 도달/근접=주황 `is-near`/여유=회색, 매수 관점) + [제거]. 국면별 종목 진입 배지(`entrySignalLabel`)는 폐기(항목3 — 국면은 현금비중만), 국면 배너는 국면명만. `TargetCell` 인라인 편집(브라우저 prompt 금지)·정렬·partial 배너 유지.
- **정렬은 순수 로직**(`lib/watchlistLogic.js`: `sortItems`·`distanceToTarget`·`classifyTargetStatus`·`detectTargetAlerts`) — 드롭다운 재정렬 시 재조회 없음. `SORT_KEYS`는 백엔드·`chat/tools.py` enum과 **SSOT 일치**. `classifyTargetStatus`는 **매수(진입가) 관점**(current≤target=도달)으로 백엔드 `_target_status`와 동일 — sell 관점으로 뒤집지 말 것.
- **능동 목표가 알림은 `App.jsx` 앱 레벨**: `far→near/reached` **전이 시에만** 주황 배너 + 브라우저 `Notification`(권한 최초 1회). 60s `setInterval` refresh(언마운트 clear). 알림은 "안내"만(주문 자동실행 금지). 목표가 도달/근접·진입 검토가능 = **주황(`--c-emph`)**, 빨강 금지.
- **[P2] `AiReportPanel`**: "AI 리포트 생성"→`POST /api/detail/{ticker}/report`→구조화 6필드 렌더(종합의견 배지 긍정적=파랑/중립=회색/**신중=주황**, 투자포인트·리스크요인·국면정합성·면책 상시). `validation_failed`면 정량요약 폴백 + "AI 서술 생성 실패" 안내. `lib/reportFormat.js::opinionTone`(순수)이 종합의견→토큰 매핑.
- **관심종목 별 토글(항목7) — `WatchlistStar.jsx`**: `StockReportView` 헤더(종목명 옆 `.report__name-row`)에 배치. **캡슐화 위젯**이 자체 `fetchWatchlistMembership(ticker)`(환각 차단)로 ★(등록완료)/☆(미등록) 표시 → 클릭 토글: 미등록→`addWatchlist({ticker,stockName})`·등록→`removeWatchlist(ticker)`. **등록완료 식별 = 주황 소프트 채움 ★**(`--c-emph`, 강조/확인 — 가격방향색 아님), 미등록 ☆=회색. `aria-pressed`·`aria-label`·busy disabled. **사용자 명시적 클릭만**(자동 아님), 409 상한은 `addErrorMessage`로 회색 안내(무한 스피너 없음), 불량 ticker 는 렌더 안 함(`isValidTicker` SSOT). 백엔드 변경 0(기존 워치리스트 API 재사용). 레거시 `StockReport.jsx`(죽은 코드·미마운트)는 손대지 않음.

## 유저베이스 — 로그인 게이트·대화기록·시황 (Phase 1~5)
- **인증 게이트**: `App`이 마운트 시 `auth.fetchMe`로 로그인 확인 — 비로그인은 `LoginScreen`(전체 게이트), 로그인 시 톱바에 이메일+로그아웃. `auth.js`: 토큰 localStorage·`authFetch`(Bearer 주입)·login/signup/me/logout. **유저별 호출(관심종목·챗·대화)은 authFetch**로.
- **대화기록**: `App`이 대화 목록·현재 대화 소유(로그인 후 로드·최소 1개 보장). 챗 `session_id = conversation.id`(문자열). `ChatPanel`: 대화 전환 시 저장 메시지 복원(`fetchConversationMessages`, DB role→bot/user 매핑) + 헤더 대화 스위처(드롭다운 + **+ 새 대화**). `newConversation`/`selectConversation`.
- **시황 요약**(Phase 1): `MarketOutlookSection`(자체조회 `/api/macro/market-outlook`)이 시장 국면 패널(`RightPanel` macro_dashboard) RegimeGauge 아래. 시황=증권사 리포트 인용(시장 판정 아님·면책). "네이버 최신 시황 가져오기"(`POST …/fetch`).
- **시황 UX(항목4): 일별 구분 + 컴팩트 3줄 카드 + 클릭 상세 오버레이**. `lib/marketOutlook.js`(순수) `groupReportsByDate`(작성일별 그룹, 날짜 결측=맨 끝)·`threeLineSummary`(응답 `summary.세줄요약` 우선, 없으면 `핵심요지[:3]` 폴백). 카드=증권사·시장전망 칩(중립 톤)·제목·3줄요약(`<button>`, 키보드 접근) → 클릭 시 `MarketOutlookDetailOverlay`(딤 배경 `--c-overlay` + 중앙 카드, ✕/Esc/배경클릭 닫힘·`role="dialog"` aria-modal·닫기버튼 포커스·트리거 복원·배경 스크롤 잠금). **모달 폐기 관습의 의도적 예외**(사용자 결정, 시황 상세 전용 — 범용 `Modal.jsx` 부활 아님, React DOM 오버레이라 이벤트 블로킹 없음). SSE fetch(`FetchProgress`)·면책 상시는 불변.
- 테스트: `App.test`·jsdom은 `./auth.js`(fetchMe 로그인됨)·`./api.js`(fetchConversations 등)를 mock. `auth.test.js`는 Node22 전역 localStorage 미비 → `vi.stubGlobal('localStorage', 인메모리)`.
