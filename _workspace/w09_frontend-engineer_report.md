# W09 frontend-engineer — 챗봇 UI + 팝업 모달 + 라우팅

작업 #8. TDD(Red→Green→Refactor). 라우팅 순수함수를 `src/lib/`로 분리해 vitest로 검증(경계면 계약만, 스냅샷 남발 금지).
계약 소비: llm-engineer `chat/tools.py`(TOOLS 3종 name·args) + chat 응답 `{text, popups:[{name,args}]}`.

## 테스트 목록(스펙 근거) → 구현 (test-first 증거)

### `src/lib/popupRouter.test.js` (17 케이스) — 팝업 라우팅 계약 + ticker 형식 가드
Red(스켈레톤 `POPUP_KIND={}`·`routePopup→null` → assertion 7 실패 확인) → Green(`src/lib/popupRouter.js`):
- `routePopup(popup)` — name 3종 → kind 분기(`show_stock_report→stock_report`, `show_macro_dashboard→macro_dashboard`, `show_watchlist→watchlist`) / args 보존(ticker·focus·highlight·sort_by) / args 결측 시 `{}` 기본 / **미지의 name(예 `order_stock`)→null**(임의 컴포넌트 렌더·주입 금지) / name 결측·비객체·숫자→null
- `routePopups(popups)` — 유효 팝업 순서 매핑 / 미지 name 필터링 / 비배열·결측→`[]` / 빈 배열(text-only·risk_guardrail 차단)→`[]`
- `POPUP_KIND` — 정확히 3종 툴 이름만 매핑(오발동 방지, 계약 SSOT)

**ticker 형식 가드(QA 관찰·team-lead 반영, SSOT 통일)** — `src/lib/ticker.js::isValidTicker` 단일 헬퍼로 분리:
- 규칙 = **`/^[0-9A-Za-z]{6}$/`(6자 영숫자)** — 기존 StockReport 직접입력 규칙에 통일(team-lead 결정: numeric 강제가 아니라 "명백한 불량 차단"; 직접입력이 받는 코드를 팝업이 거부하면 UX 불일치). 영문 포함 6자 통과, 한글(종목명)·공백·자릿수 불량·결측 → false.
- **SSOT**: `StockReport.onSubmit`(직접입력)과 `popupRouter.routePopup`(팝업)이 같은 `isValidTicker`를 import. 기존 인라인 정규식 `/^[0-9A-Za-z]{6}$/`(StockReport) 제거 → 규칙은 `ticker.js` 한 곳에만(중복 grep 0, 주석 제외).
- `routePopup` — stock_report 는 `valid=isValidTicker(args.ticker)`, 그 외 kind 는 `valid=true`. **불량 ticker 는 kind 는 유지하되 valid=false** → `ChatPanel.PopupBody` 가 fetchStockBundle 호출 없이 "종목 코드를 인식하지 못했어요…" graceful 안내(잘못된 코드로 백엔드 조회 방지).
- 테스트: `src/lib/ticker.test.js`(형식 규칙, 영숫자 통과 포함) 신규 + `popupRouter.test.js` routePopup valid 분기. Red(스켈레톤 `return false`→영숫자 통과 실패)→Green.

**결과: `npx vitest run` → 4 files, 40 passed**(기존 21 + popupRouter 라우팅 11 + ticker.js 5 + routePopup valid 3). `npm run build` → 0 error.

## 컴포넌트 ↔ 팝업 툴 매핑표 (라우팅 계약)

| 팝업 툴(name) | routePopup kind | 컴포넌트 | 실데이터 조회(프론트 직접) | args 사용 |
|---|---|---|---|---|
| `show_stock_report` | `stock_report` | `PopupStockReport` → `StockReportView` 재사용 (ticker 6자리 숫자일 때만; 불량 시 조회 없이 안내) | `fetchStockBundle(args.ticker)` 1회(N+1 금지, 무캐시 매 조회) | `ticker`(6자리 숫자 검증)·`stock_name`(모달 제목)·`focus`(뷰가 해석) |
| `show_macro_dashboard` | `macro_dashboard` | `RegimeGauge` 재사용 | `fetchMacroRegime()` 자체 조회(마운트 시, 무캐시) | `highlight`(통과) |
| `show_watchlist` | `watchlist` | `PopupWatchlist` | 없음(W10 플레이스홀더) | `sort_by`(라벨 표시) |
| (미지 name) | null | 렌더 안 함 | — | — |

- 라우팅은 **name 으로만** 분기, enum args 는 통과시켜 컴포넌트가 해석(계약 최소 결합). 미지 name 은 조용히 제외.
- 팝업 실데이터는 **LLM 응답이 아니라 프론트가 API 로 직접 조회**(환각 차단 + 최신성). 현재가·번들·국면은 팝업 열 때마다 조회(무캐시).

## chat 응답 처리 (text / popups 분리)
- `postChat(sessionId, message)` → `POST /api/chat {session_id, message}` → `{text, popups}`.
- `text` → 봇 말풍선(줄바꿈 pre-wrap). `popups` → `routePopups` → 자동 팝업 모달 오픈 + 봇 버블 하단 "다시 열기" 칩(닫아도 재접근).
- `text` 공백 + popups 있음 → "요청하신 내용을 팝업으로 열었습니다." 폴백 문구.
- `risk_guardrail` 차단 응답(`popups:[]`) → 텍스트만 말풍선, 팝업 없음(routePopups([])→[]).

## 사용 API (프론트 → 백엔드)
- `POST /api/chat` — `src/api.js::postChat`. 챗 응답 shape 소비.
- `GET /api/detail/{ticker}/bundle` — `fetchStockBundle`(PopupStockReport, 팝업 열 때마다 1회).
- `GET /api/macro/regime` — `fetchMacroRegime`(RegimeGauge, 팝업 마운트 시).

## 신규/수정 파일
- 신규: `lib/popupRouter.js`(+`.test.js`), `components/{Modal,ChatPanel,ChatMessage,PopupStockReport,PopupWatchlist}.jsx`
- 수정: `api.js`(+postChat), `App.jsx`(+ChatPanel 섹션), `styles.css`(챗·모달 클래스), `theme.css`(+`--c-overlay` 토큰, --c-black 기반 반투명 딤)

## 세션 처리
- `session_id` = 마운트 시 `crypto.randomUUID` 1회(useRef, 폴백 포함). 서버가 히스토리 보관 → 프론트는 id+메시지만 전송.

## UI 디자인 준수 (ui-design-system)
- 사용자 버블=`--c-blue-soft`, 봇 버블=`--c-surface`. 색은 theme.css 토큰만(hex 0). 초록·황색 0.
- 챗/모달 장식에 난색(주황·빨강)·가격방향색 미사용(팔레트 규칙 준수).
- Modal: 오버레이+✕+Escape+오버레이클릭 닫기. **브라우저 modal dialog(alert/confirm/prompt) 미사용**(role="dialog"는 ARIA 시맨틱).
- 하단 **면책 고지 상시**(회색 톤, 빨강 아님) — "면허 있는 자문 아님".
- 에러: 배너 + 재시도(마지막 질문 재전송). **무한 스피너 없음**.

## 안전 게이트(프론트, grep 0 확인)
- 주문 API 참조 0(`order_cash|buy_order|sell_order|주문` grep 0) · 신규 파일 하드코딩 hex 0(theme.css=SSOT) ·
  챗/모달 초록·황색 0 · `alert/confirm/prompt` 0 · 팝업 실데이터 무캐시 직접 조회(fetchStockBundle/fetchMacroRegime 매 오픈).

## 계약 확인 지점 (해결됨)
1. **팝업 툴 이름·args → `chat/tools.py`와 대조 확정**: name 3종·`show_stock_report.required=[ticker]`·enum(focus/highlight/sort_by) 정확히 일치. routePopup은 name 기준 분기라 enum 변경에 무영향.
2. chat 응답 shape `{text, popups:[{name,args}]}`·args=dict(파싱된 tool 인자) 가정 — llm-engineer #6(chat.py) 완료 시 SendMessage로 최종 확정 요청함(불일치 시 즉시 수정).
