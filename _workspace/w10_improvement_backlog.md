# W10 개선 백로그 (코드리뷰 워크플로우 산출, 39발견→30검증→20병합)

총평: 활성 버그 없음(안전 원칙 준수·판정은 코드·면책 상시). 개선 축 = ①국면 매핑/진입차단/target=0 판정 중복(3중 일관성 부채) ②챗봇 워치리스트 편집 제품 갭 ③저비용 하드닝(ticker 검증·KIS 동시성) ④테스트 공백(컴포넌트·라이브 e2e).

상태: [ ] 대기 · [~] 진행 · [x] 완료

## P0 (즉시 이득 큰 저비용)
- [x] IMP-01 (correctness, S) target=0 백엔드 target_status↔프론트 classify 정합화 + 죽은 프론트 복제본 제거 — watchlist/service.py:46, frontend/src/lib/watchlistLogic.js:23,35 ✅ 백403→406·프98→89
- [x] IMP-02 (safety, S) 리포트·워치리스트 라우트 {ticker} 정규식 검증(400) 공유 헬퍼 — api/deps.py(신규)·report·watchlist ✅ 백406→410
- [x] IMP-03 (correctness, S) POST 재추가 upsert reason/stock_name None 덮어쓰기 방지 폴백 — api/watchlist.py ✅ 백410→411 (버튼 멤버십 UX는 P1 후속 IMP-21로 분리)
- [x] IMP-04 (correctness, S) api.js addWatchlist 주석 계약 오류(422→400) 정정 — frontend/src/api.js:85 ✅

## P1 (명확한 개선)
- [x] IMP-05 (correctness, S) stock_name 라이브 폴백 inquire_price→stock_info.search_stock_info(죽은 코드) — api/watchlist.py ✅ 백411→414
- [x] IMP-06 (architecture, M) 국면 매핑·빌더 → api/deps.py SSOT(_REGIME_INPUT_MAP·map_engine_input·build_judgement) — main.live_judgement patch 지점 보존 ✅ 백414→425(테스트 변경 0)
- [x] IMP-07 (safety, S) 리포트 프롬프트 국면 결측 표면화 + entry_blocked/밸류초과 게이트 + ENTRY_SIGNAL_RULES 공유(build_prompt) — chat/report.py·build_prompt.py ✅ 백425→430
- [ ] IMP-08 (product, M) 챗봇 자연어 워치리스트 편집 manage_watchlist(add/remove/set_target) 툴 — chat/tools.py, api/chat.py
- [ ] IMP-09 (architecture, S) 워치리스트 KIS 병렬 max_workers 고정 상한(5~8) + 팝업/패널 이중 마운트 정리 — watchlist/service.py:109
- [ ] IMP-10 (ux, S) 인라인 편집/삭제 실패 피드백을 view 존재 시에도 표시 — WatchlistView.jsx:89-106
- [ ] IMP-11 (ux, S) 목표가 알림 권한요청을 사용자 제스처(CTA)에 결합 — App.jsx:45
- [ ] IMP-21 (ux, M) StockReport 관심종목 버튼 멤버십 인지(담김→'제거'만/아니면'추가'만) + 경량 GET /api/watchlist/{ticker} 멤버십 엔드포인트 — IMP-03에서 분리

## P2 (여유 시)
- [ ] IMP-12 (architecture, S) 리포트 라우트 _get_store() 간접 진입점(watchlist 패턴 통일)
- [ ] IMP-13 (architecture, S) JSON-파일 Store 원자적 write 공통 헬퍼 AtomicJsonFile
- [ ] IMP-14 (safety, S) 면책고지·요약·리스크 min_length 강화 + 과대 주석 정정
- [ ] IMP-15 (safety, S) AiReportPanel 자족 코드고정 면책 이중화 + regime_block entry_blocked 파생
- [ ] IMP-16 (product, S) 리포트 히스토리 중복저장 게이트 + 상한 + 과거대비 비교 UI
- [ ] IMP-17 (tests, M) 프론트 컴포넌트 렌더 테스트 인프라(jsdom+@testing-library)
- [ ] IMP-18 (tests, S) api.main W10 wiring(라우터 include+CORS) 회귀 스모크
- [ ] IMP-19 (tests, S) 리포트 라이브 e2e(-m live) gpt-5.4 실 JSON 스키마 충족
- [ ] IMP-20 (tests, M) Store 동시성(threading.Lock) 회귀 테스트
