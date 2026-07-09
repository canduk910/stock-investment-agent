# frontend/ — React + Vite

## 실행
- 백엔드 먼저: `uv run uvicorn api.main:app --port 8000` → 프론트: `npm run dev`.
- **`http://localhost:5173`로 연다** — Vite가 IPv6 localhost에 바인딩하므로 `127.0.0.1:5173`은 안 될 수 있다.
- Vite dev가 `/api`를 `http://127.0.0.1:8000`으로 프록시 → 개발 중 CORS 불필요.

## 디자인 (반드시 준수)
- 팔레트는 **흰색/회색/파랑/남색/검정 5계열 + 강조 주황(`--c-emph`) + 위험 빨강(`--c-danger`)**. 초록·황색 금지. 상승=파랑, 하락=회색. **주황=강조**(권장 현금비중·국면명), **빨강=위험**(손실경고·VIX 패닉만) — 두 난색은 역할을 섞지 않고 가격 방향·장식엔 금지.
- 색은 **`src/theme.css` 토큰(`var(--c-*)`)만** 참조. 컴포넌트에 hex 하드코딩 금지. 전체 규칙: `ui-design-system` 스킬.
- **예외 — 캔들차트(KLineChartPanel)**: 한국 관습 **상승=빨강(`--c-chart-up`)/하락=파랑(`--c-chart-down`)**(사용자 결정). `lib/theme.js::readChartPalette`가 이 토큰을 klinecharts 캔들에만 주입. 지표선(MA/RSI)·52주/현재가선은 남색·회색으로 캔들과 구분. 차트 밖은 전역 규칙(파랑=상승/회색=하락) 유지 — 이 예외를 위반으로 오해해 되돌리지 말 것.

## 계약
- `GET /api/macro/indicators` → `{indicators, partial_failure}` 소비. 지표가 `null`이면 "일시 조회 불가" 카드로 표시하고 나머지는 정상 렌더(부분 실패 보존). 지표 키·shape은 백엔드(`api/main.py`)와 일치해야 한다.
- 화면은 단계적으로 성장: 1단계 지표 대시보드 → W07 국면 게이지 → W08 종목 리포트 → W09 챗봇/팝업 → **W10 워치리스트·구조화 리포트(완료)**. 새 화면도 같은 토큰을 조합해 한 제품처럼 보이게.

## 챗봇 (W09)
- **응답은 SSE 스트리밍**(`postChatStream`→`POST /api/chat/stream`)이 기본, `postChat`(논스트림)은 폴백. `lib/sseChat.js`의 `parseSSEBuffer`(순수함수)가 `\n\n` 경계로 이벤트를 재조립한다 — 청크가 경계를 가로질러/여러 이벤트가 한 청크로 오는 경우 방어(TextDecoder `stream:true`). 이벤트 `{type:stage|token|popups|done}`, stage enum은 `lib/chatStages.js`가 백엔드와 **SSOT로 공유**.
- `ChatPanel`은 스트리밍 상태기계: 봇 placeholder를 만들고 `onStage`(진행 체크리스트)·`onToken`(라이브 타이핑)·`onDone`(→`routePopups`→모달) 갱신. 스트림 실패 시 `postChat` 폴백 1회. streaming 중 입력 비활성, 무한 스피너 금지(에러 배너+재시도).
- **팝업 실데이터는 LLM 응답이 아니라 프론트가 직접 조회**(환각 차단): `popups[].name`→`lib/popupRouter.js`가 컴포넌트로 라우팅(show_stock_report→번들 API, show_macro_dashboard→regime API). LLM은 "무엇을 띄울지"만 준다.
- **ticker 유효성은 `lib/ticker.js` 단일 출처**(`/^[0-9A-Za-z]{6}$/`) — 직접입력(StockReport)과 팝업 라우팅이 공유. 불량 코드는 조회 없이 안내로 graceful 처리.
- 챗 신규 UI도 `theme.css` 토큰만(hex/초록/황색 0), 면책 고지 상시 노출.

## 로컬 도커 기동 (대안 실행)
- `docker compose up --build` → `localhost:5173`(프론트)+`:8000`(백엔드). 시크릿은 `.env` 런타임 주입(`env_file`), 소스 핫리로드. Vite 프록시 대상은 `VITE_PROXY_TARGET`로 재정의(도커=`http://backend:8000`). 상세는 루트 `DOCKER.md`.

## 워치리스트 + 구조화 리포트 (W10)
- **`WatchlistView`는 팝업 겸 독립 페이지 단일 컴포넌트** — `PopupWatchlist`(모달)와 `App` 4번째 패널이 같은 본문을 공유. 실데이터는 프론트가 `/api/watchlist`로 직접 조회(환각 차단). `popupRouter`의 `show_watchlist→watchlist` 계약 유지.
- **정렬은 순수 로직**(`lib/watchlistLogic.js`: `sortItems`·`distanceToTarget`·`classifyTargetStatus`·`detectTargetAlerts`) — 드롭다운 재정렬 시 재조회 없음. `SORT_KEYS`는 백엔드·`chat/tools.py` enum과 **SSOT 일치**. `classifyTargetStatus`는 **매수(진입가) 관점**(current≤target=도달)으로 백엔드 `_target_status`와 동일 — sell 관점으로 뒤집지 말 것.
- **능동 목표가 알림은 `App.jsx` 앱 레벨**: `far→near/reached` **전이 시에만** 주황 배너 + 브라우저 `Notification`(권한 최초 1회). 60s `setInterval` refresh(언마운트 clear). 알림은 "안내"만(주문 자동실행 금지). 목표가 도달/근접·진입 검토가능 = **주황(`--c-emph`)**, 빨강 금지.
- **[P2] `AiReportPanel`**: "AI 리포트 생성"→`POST /api/detail/{ticker}/report`→구조화 6필드 렌더(종합의견 배지 긍정적=파랑/중립=회색/**신중=주황**, 투자포인트·리스크요인·국면정합성·면책 상시). `validation_failed`면 정량요약 폴백 + "AI 서술 생성 실패" 안내. `lib/reportFormat.js::opinionTone`(순수)이 종합의견→토큰 매핑.
