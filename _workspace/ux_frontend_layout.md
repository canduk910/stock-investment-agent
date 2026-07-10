# UX1+UX4 — 2컬럼 레이아웃 + 우측 동적 패널 + 잔고 패널 (frontend-engineer-2)

Task #11(UX1)·#14(UX4) 완료. TDD Red→Green. 모달 완전 폐기 → 우측 인라인 패널. 팝업 컴포넌트 재작성 0(전부 인라인 재사용). 색은 theme.css 토큰만.

## 테스트 목록 (스펙 근거 → 구현 순서, test-first)

### RightPanel.test.jsx (신규 13) — 계획 §Phase A "RightPanel"
- 본문 라우팅(spec.kind → 인라인 컴포넌트): watchlist→PopupWatchlist, macro_dashboard→RegimeGauge, stock_report(valid)→PopupStockReport, stock_report(invalid)→안내(조회 없음), **balance→BalancePanel**, manage_watchlist→ManageWatchlistConfirm, null→빈 상태(퀵버튼).
- 퀵버튼 툴바(onSelect 리프팅): 국면→macro_dashboard, 관심종목→watchlist, 잔고→balance, 종목검색(유효 ticker→stock_report / 불량→미호출, isValidTicker SSOT), 활성 kind aria-pressed.

### App.test.jsx (신규 5) — 계획 §Phase A "App.jsx"
- 랜딩=watchlist 우측 렌더 · ChatPanel onShowPanel→우측 전환(채팅 구동) · RightPanel 퀵버튼 onSelect→우측 전환(직접 탐색).
- 목표가 App레벨 폴링(IMP-11 보존): far→reached 전이 배너, first-observation 무발화(마운트 무더기 방지).

### popupRouter.test.js (갱신) — llm UX3 계약
- `show_balance → kind 'balance'`(무파라미터, valid true) · POPUP_KIND 5종 계약(4→5).

### BalancePanel.test.jsx (신규 5) — 계획 §Phase B "프론트" · data UX2 shape
- 요약카드+보유종목표(종목명·손익)·면책 상시 · 손익 색(이익=.up/손실=.down, 빨강 금지) · 부분실패(holdings=null·partial_failure:[balance])→"일시 조회 불가" · 보유0 빈안내 · HTTP오류→재시도.
- **경계 mock = global.fetch**(api.js fetchBalance 실코드 통과). 이유: rejected-promise mock(mockRejectedValue/async throw)은 catch 등록 직전 microtask에 vitest4+jsdom unhandledRejection 오탐(에러 UI는 정상 렌더 확인). fetch 경계 mock으로 fetchBalance의 throw가 컴포넌트 내부에서 자연 발생 → 오탐 없음 + "경계만 mock" 원칙 부합.

**Red 확인**: RightPanel/App(import·assert 실패), popupRouter(5종·balance 미매핑 실패), BalancePanel(컴포넌트 없음). → Green 후 전체 128 passed.

## 구현 (Green)

### UX1 (모달 폐기 + 2컬럼)
- **App.jsx**: 세로 스택 제거 → `.app__main` 2컬럼 그리드(좌 ChatPanel / 우 RightPanel), 반응형 ~1024px 세로. `rightPanelSpec` 상태 리프팅(랜딩 LANDING_SPEC={kind:'watchlist'}). 목표가 60s 폴링 App레벨 이관(fetchWatchlist+detectTargetAlerts+Notification 재사용) — 패널 무관. MacroDashboard/StockReport import·렌더 제거.
- **RightPanel.jsx**(신규): 퀵버튼 툴바(QUICK_BUTTONS 3종+종목검색 인라인 폼) + 헤더(PANEL_TITLE·닫기) + RightPanelBody switch(ChatPanel.PopupBody 이관+balance). 빈 상태=탐색 유도.
- **ChatPanel.jsx**: Modal import·렌더·popupQueue/activePopup/closePopup 제거. finishStream이 showPanel(routePopups[0])→onShowPanel. onOpenPopup→onShowPanel. section `dashboard` 클래스 제거(좌측 컬럼 flex).
- **Modal.jsx 삭제**. 죽은 `.modal*`·`.watchlist-page__*` CSS 제거. `--c-overlay` 토큰은 theme.css에 정의만 잔존(무해).

### UX4 (잔고)
- **api.js**: `fetchBalance()`(GET /api/balance, 무캐시·조회전용).
- **BalancePanel.jsx**(신규): 자체조회 → 요약카드(예수금·매입액·평가액·평가손익·순자산) + 보유종목표(종목·수량·평단·현재가·평가액·손익/수익률). 손익=글로벌 상승파랑/하락회색(빨강 금지, WatchlistView 등락률과 동일). 순자산=강조 주황. 조회시점·면책 상시. 부분실패 graceful. HTTP오류 재시도.
- **popupRouter.js**: `POPUP_KIND.show_balance='balance'`(5종).
- **RightPanel.jsx**: RightPanelBody `case 'balance' → <BalancePanel />`.
- **styles.css**: `.app*`·`.right-panel*`·`.balance*` 룰 추가(전부 var 토큰).

## 컴포넌트 ↔ 팝업 툴(kind) 매핑표

| 툴 이름(llm) | POPUP_KIND | RightPanelBody case | 컴포넌트 | 자체조회 API |
|---|---|---|---|---|
| show_stock_report | stock_report | stock_report | PopupStockReport→StockReportView | GET /api/detail/{ticker}/bundle |
| show_macro_dashboard | macro_dashboard | macro_dashboard | RegimeGauge | GET /api/macro/regime |
| show_watchlist | watchlist | watchlist | PopupWatchlist→WatchlistView | GET /api/watchlist |
| **show_balance** | **balance** | **balance** | **BalancePanel** | **GET /api/balance** |
| manage_watchlist | manage_watchlist | manage_watchlist | ManageWatchlistConfirm | POST/DELETE/PATCH /api/watchlist(확인 후) |

퀵버튼(대화 없이 직접 탐색): 국면→macro_dashboard · 관심종목→watchlist · 잔고→balance · 종목검색→stock_report(isValidTicker).

## 사용 API 엔드포인트
- GET /api/watchlist (App 폴링 + WatchlistView)
- GET /api/macro/regime (RegimeGauge)
- GET /api/detail/{ticker}/bundle (PopupStockReport)
- GET /api/balance (BalancePanel) — 신규 소비
- POST/DELETE/PATCH /api/watchlist (ManageWatchlistConfirm, 확인 후)

## 검증
- `cd frontend && npm test` → **128 passed**(13 files). 기존 104 + App 5 + RightPanel 13 + BalancePanel 5 + popupRouter balance 1.
- `npx vite build` → clean(53 modules).
- 안전 grep: 신규 컴포넌트/CSS 하드코딩 hex 0 · 초록/황색 0 · 주문 API 0 · 손익 색=파랑/회색(danger·chart 토큰 오용 0) · 면책 상시(BalancePanel·ChatPanel).

## qa-inspector 참고
- 경계면: llm POPUP_KIND(5종 enum) ↔ popupRouter.POPUP_KIND ↔ RightPanelBody switch case — 5종 전수 일치 확인. data /api/balance shape ↔ BalancePanel 필드(holdings/summary 키) 일치.
- 테스트 인프라 노트: BalancePanel error-state는 fetch 경계 mock 사용(rejected-promise mock의 vitest4 오탐 회피). 다른 컴포넌트 테스트는 기존 api.js mock 방식 유지(정상 경로라 무영향). vite.config·setup.js 변경 없음.
