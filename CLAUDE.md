# stock-investment-agent

개인 투자자용 금융 분석 AI Agent (연세대 과제, WEEK 06~10). 원본 스펙: `invest_develop_PLAN.md` — 모든 구현 판단의 최종 기준.

## 하네스: 투자 에이전트 개발

**목표:** `invest_develop_PLAN.md`의 5주 로드맵(데이터 파이프라인 → 매크로 엔진 → 종목 리포트 → 챗봇 → 워치리스트)을 에이전트 팀으로 구현한다.

**트리거:** 개발 진행·구현·주차(WEEK) 작업·모듈 개발(매크로/종목/챗봇/프론트/데이터)·버그 픽스·QA 검증 요청 시 `invest-dev` 스킬을 사용하라. 단순 질문(코드 설명, 스펙 문의)은 직접 응답 가능.

**핵심 안전 원칙 (모든 세션에서 유지):** 매매 주문 API 절대 구현·호출 금지(조회만), LLM은 설명만(판정은 코드), 임계값 3중 일관성, 현재가 캐시 금지, 모든 구현은 TDD(테스트 먼저 — `tdd-workflow` 스킬). KIS API 코드는 kis-code-assistant MCP로 검증된 코드를 먼저 검색한다.

**UI 디자인 톤:** 모든 화면은 **흰색/회색/파랑/남색/검정 5계열 + 강조 주황(`--c-emph`) + 위험 빨강(`--c-danger`)** 팔레트로 통일한다(초록·황색 배제, 상승/하락은 파랑·회색으로 — 단 **종목 캔들차트·등락률만** 한국 관습 상승=빨강/하락=파랑 예외 `--c-chart-up/down`). **주황=강조**(권장 현금비중·국면명 등 핵심 값), **빨강=위험**(손실경고·VIX 패닉만). 난색 두 색은 역할을 섞지 않고, 가격 방향·장식엔 금지. 색은 `frontend/src/theme.css` 토큰(`var(--c-...)`)이 단일 출처 — 하드코딩 금지. 상세는 `ui-design-system` 스킬. UI 작업 시 frontend-engineer가 이 스킬을 먼저 읽는다.

## 현황 (WEEK 08 완료)

데이터 파이프라인 · 매크로 2축 판정 대시보드 + **종목 종합리포트**(번들 API·정량요약·캔들차트·예측 PER·avg_per 라이브 게이트·종목명 자동완성) 동작. 다음: WEEK 09 LLM 챗봇(agent 루프·팝업 function calling — 구현 골격은 `llm-safety-guide/references/llm-agent-patterns.md`). 실행: 백엔드 `uv run uvicorn api.main:app --port 8000` + 프론트 `cd frontend && npm run dev` → `localhost:5173`. 테스트 `uv run pytest`(218개; 라이브는 `-m live`, 키 필요).

## 디렉토리 문서 지도

기능별 세부 지식(결정·함정·계약)은 각 디렉토리 `CLAUDE.md`에 있다(해당 디렉토리 작업 시 자동 로드):
- `collectors/CLAUDE.md` — KIS 어댑터(오류 표면화·토큰 backoff·라이브 확정 필드명)·지표 수집기 계약
- `cache/CLAUDE.md` — 캐시 3원칙의 구조적 강제 + 클라우드 전환 계약
- `api/CLAUDE.md` — FastAPI = Lambda 로컬 스탠드인, 엔드포인트 계약
- `frontend/CLAUDE.md` — 실행법(IPv6 localhost)·디자인 토큰·API 계약

**변경 이력:**
| 날짜 | 변경 내용 | 대상 | 사유 |
|------|----------|------|------|
| 2026-07-05 | 초기 구성 (에이전트 5 + 스킬 5) | 전체 | - |
| 2026-07-05 | 팀 도구 매핑 명시(Agent+SendMessage+Task*), KIS 미확정 함수 분리, 설명 질문 트리거 제외 | skills/invest-dev, skills/kis-data-pipeline | 정합성 감사 권고 반영 |
| 2026-07-05 | TDD 원칙 내장: tdd-workflow 스킬 신설, 구현 에이전트 4명 TDD 원칙 추가, QA에 TDD 준수 검증(§3.5) 추가, 오케스트레이터 Red→Green→Refactor 강제 | skills/tdd-workflow(신규), agents/*, skills/invest-qa-checklist, skills/invest-dev, skills/quant-engine-rules | 사용자 요청: 구축 흐름에 TDD 적용 |
| 2026-07-05 | UI 디자인 시스템 신설: 흰색/회색/파랑/남색/검정 팔레트 + theme.css 토큰 SSOT, frontend-engineer 원칙0에 반영, 대시보드 라이트 톤 적용 | skills/ui-design-system(신규), agents/frontend-engineer, frontend/src/theme.css·styles.css | 사용자 요청: UI 톤 통일 |
| 2026-07-05 | doc-commit 스킬 신설, W06 완료 + 디렉토리별 CLAUDE.md 정리(collectors/cache/api/frontend), 첫 커밋 | skills/doc-commit(신규), 각 디렉토리 CLAUDE.md, CLAUDE.md | 사용자 요청: 진행상황 문서화 후 커밋/푸시 |
| 2026-07-06 | W07 매크로 엔진(2축 경기×심리 + 역발상 현금비중) + /api/macro/regime + 2×2 게이지 UI | macro/(engine·CLAUDE), api/, frontend/(RegimeGauge) | 사용자 결정: 2축 판정 + 역발상 |
| 2026-07-06 | UI 강조/위험 색 체계: 주황(강조)·빨강(위험) 토큰 추가, 2×2 위치 점·국면 해설 | skills/ui-design-system, frontend/theme·styles | 사용자 요청: 강조=주황, 위험=빨강 |
| 2026-07-07 | W08 종목 종합리포트: 정량요약 엔진(CAGR·avg_per 자기과거평균·RSI/MA/52주·regime_gate 역발상) + KIS 어댑터 4종(현재가·손익·재무비율·추정실적)+번들 API(partial_failure·캐시게이트) + 예측 PER(리서치 컨센서스, 후행 PER 보완) + KLineChartPanel(klinecharts) + 종목명 자동완성(KIS 마스터). avg_per는 라이브 검증 게이트. 218 tests green | stock/·collectors/·api/·frontend/ + 각 CLAUDE.md | WEEK 08 로드맵 + 사용자 요청(예측 PER·자동완성) |
| 2026-07-07 | 캔들차트·등락률 한국 관습색(상승=빨강/하락=파랑) — 팔레트 유일 예외로 문서화(theme.css `--c-chart-*`); LLM agent 패턴 추출(강의 노트북→llm-safety-guide references, 노트북 삭제) | skills/ui-design-system·llm-safety-guide(신규 references), frontend/theme·styles·theme.js, collectors·frontend CLAUDE.md | 사용자 요청: 한국식 차트색 + 노트북 LLM로직 지침 반영 후 삭제 |
