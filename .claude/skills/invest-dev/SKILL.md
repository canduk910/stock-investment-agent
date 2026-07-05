---
name: invest-dev
description: "금융 투자 AI Agent(invest_develop_PLAN.md) 개발 팀을 조율하는 오케스트레이터. 개발 진행, 구현 시작, WEEK 06~10 주차 작업, 매크로 엔진/데이터 파이프라인/종목 리포트/챗봇/워치리스트/프론트엔드 구현 요청 시 반드시 사용. 후속 작업: 다시 실행, 재실행, 이어서 개발, 수정, 보완, 버그 픽스, 특정 모듈만 다시, 이전 결과 개선, QA 재검증 요청 시에도 반드시 이 스킬을 사용. 단, '~가 뭐야', '어떻게 동작해', '왜 이 값이야' 류 설명·질문에는 이 스킬을 트리거하지 말고 직접 응답할 것 — 코드 변경 의도가 있을 때만 사용."
---

# Invest-Dev Orchestrator — 투자 에이전트 개발 팀 조율

`invest_develop_PLAN.md`(원본 스펙, 항상 우선)를 5주 로드맵에 따라 구현하는 에이전트 팀을 조율한다.

## 실행 모드: 에이전트 팀

경계면 계약(번들 API shape, 팝업 툴 정의, 판정 스키마)이 에이전트 간 실시간으로 오가야 하고, QA가 각 모듈 완성 직후 개입(incremental QA)해야 하므로 팀 모드가 필수다.

## 에이전트 구성

| 팀원 | agent_type | 역할 | 스킬 | 주 활동 주차 |
|------|-----------|------|------|------------|
| data-engineer | general-purpose | KIS/DART/FRED/CNN 수집기·캐시·번들 API | kis-data-pipeline + tdd-workflow | W06, W08 |
| quant-engineer | general-purpose | macro_engine·stock_summary·단위테스트 | quant-engine-rules + tdd-workflow | W07, W08 |
| llm-engineer | general-purpose | build_prompt·chat·인텐트·스키마 | llm-safety-guide + tdd-workflow | W09 |
| frontend-engineer | general-purpose | React 컴포넌트·팝업 라우팅 | tdd-workflow (+ llm-safety-guide §2 계약 참조) | W08~W10 |
| qa-inspector | general-purpose | 경계면 교차 검증·안전 점검·TDD 준수 확인 | invest-qa-checklist | 전 주차 (incremental) |

**TDD 원칙 (전 구현 작업 공통)**: 모든 구현 팀원은 `tdd-workflow` 스킬의 Red→Green→Refactor 사이클을 따른다. 구현 코드보다 실패하는 테스트가 먼저다.

- 모든 팀원 스폰 시 `model: "opus"` 명시
- 각 팀원의 상세 프로토콜은 `.claude/agents/{name}.md` 정의를 프롬프트에 포함해 전달
- **한 번에 전원을 띄우지 않는다** — 요청된 주차/모듈에 필요한 팀원 + qa-inspector만 스폰 (팀원 3~4명이 적정)

## 워크플로우

### Phase 0: 컨텍스트 확인 (후속 작업 지원)

1. `_workspace/` 존재 여부 확인
   - **미존재** → 초기 실행 (Phase 1)
   - **존재 + 부분 수정/버그 픽스 요청** → 부분 재실행: 해당 담당 에이전트 + qa-inspector만 스폰. 이전 산출물 경로를 프롬프트에 포함
   - **존재 + 새 주차 진행 요청** → 이어서 실행: 이전 주차 산출물(`_workspace/` 명세)을 새 팀원의 입력으로 연결
2. 프로젝트 코드 현황을 훑어 어느 주차까지 완료됐는지 파악 (`_workspace/` 요약과 실제 코드 대조)
3. 사용자 요청이 특정 주차/모듈을 지정하지 않으면, 현황상 다음 주차를 제안하고 진행

### Phase 1: 준비 (초기 실행 시)

1. 프로젝트 스캐폴딩: `/macro`, `/stock`, `/chat`, `/collectors`, `/cache`, `/frontend`, `/infra`, `_workspace/`, `.env.example`
2. `invest_develop_PLAN.md`에서 해당 주차의 P1/P2 항목 추출 → 작업 목록 초안

### Phase 2: 팀 구성

> **툴 매핑 주의**: 이 환경에 TeamCreate/TeamDelete 도구는 없다. "팀 구성" = `Agent` 도구로 팀원을 `name` 지정 + `run_in_background: true`로 스폰하는 것이고, 이후 `SendMessage(to: name)`으로 통신한다. 작업 목록은 `TaskCreate`/`TaskUpdate`/`TaskList`를 사용한다(ToolSearch로 스키마 선로드). "팀 정리" = 각 팀원에게 종료 SendMessage 후 필요 시 TaskStop.

1. 팀원 스폰: 해당 주차 팀원 + qa-inspector를 `Agent(name: "{팀원명}", model: "opus", run_in_background: true)`로 스폰 — prompt에 `.claude/agents/{name}.md` 정의 내용 + 주차 작업 범위 + `_workspace/` 입출력 경로 + 다른 팀원 이름(SendMessage 대상) 포함
2. `TaskCreate`로 주차별 작업 등록 (아래 주차별 작업표 참조). 의존 작업은 의존 관계를 명시하고, QA 검증 작업은 각 구현 작업 완료에 의존하도록 등록
3. **TDD 작업 분할**: 각 구현 작업의 description에 "① 스펙에서 테스트 도출·작성·실패 확인(Red) ② 최소 구현(Green) ③ 리팩토링" 순서를 명시한다. 테스트 작성이 별도 작업으로 분리될 만큼 크면(예: W07 경계값 스위트) 독립 작업으로 등록하고 구현 작업이 이에 의존하게 한다

### 주차별 작업표 (플랜 §9 기준 — P1은 필수, P2는 여유 시)

| 주차 | 주 담당 | 핵심 작업 | QA 검증 포인트 |
|------|--------|----------|---------------|
| W06 | data-engineer | KIS 인증·조회 함수(MCP 워크플로우), FRED/공포탐욕 수집기 3~4개, 캐시(3원칙), AWS 기본 | 안전 grep, 캐시 정책, 수집기 반환 shape |
| W07 | quant-engineer | macro_engine(투표→판정→현금비중), VIX 오버라이드, 격차 신뢰도, REGIME_PARAMS, 단위테스트 | 테스트 실행, 판정 순서, 관점 통일(현금비중) |
| W08 | quant + data + frontend | stock_summary, 번들 API(병렬+partial_failure), 종목 리포트 컴포넌트 | 경계면 #1·#5·#6, 3중 일관성 |
| W09 | llm-engineer + frontend | build_prompt(자동 기준표)+chat(function calling), 인텐트 분류, 프론트 text/popups 분리 | 경계면 #2·#3·#4·#7, 프롬프트 필수 블록 |
| W10 | data + frontend (+llm) | 워치리스트 CRUD+진입신호(single_cap 게이트), 전체 통합·시연 준비 | 전체 회귀 + 안전 체크리스트 최종 |

### Phase 3: 구현 (팀원 자체 조율)

- 팀원들은 작업 목록에서 claim하고 독립 수행. 산출물 명세는 `_workspace/{week}_{agent}_{artifact}.md` — **테스트 목록(스펙 근거) → 구현 순서로 기록** (QA의 test-first 증거)
- 구현은 TDD 사이클로: 테스트 먼저 작성·실패 확인 후 구현. 테스트가 실패하면 구현을 고치고, 테스트·상수를 구현에 맞춰 바꾸지 않는다 (스펙 변경이 필요하면 리더 보고)
- **경계면 계약 통신 규칙** (필수):
  - data-engineer → 수집기/번들 API shape 확정 시 소비자(quant, frontend)에게 SendMessage
  - quant-engineer → 판정/요약 스키마·상수 구조 변경 시 llm-engineer에게 즉시 알림
  - llm-engineer → 팝업 툴 정의·chat 응답 shape 확정 시 frontend-engineer에게 전달
- **incremental QA**: 각 팀원은 모듈 완성 즉시 qa-inspector에게 검증 요청. qa-inspector는 실패 항목을 담당자에게 파일:라인으로 회신, 안전 실패는 리더에게 즉시 보고
- 리더는 TaskList/TaskGet으로 진행률 모니터링, 막힌 팀원에게 SendMessage 개입

### Phase 4: 통합 검증

1. 전 작업 완료 대기 → qa-inspector에게 주차 단위 통합 검증 지시 (경계면 표 전체 + 안전 grep + 전체 테스트 스위트 실행·TDD 준수 확인)
2. QA 실패 → 담당 에이전트 수정 → 재검증 (최대 2회 루프, 이후 리더 판단)
3. 주차 산출물 확인: 플랜 §9의 "산출물" 기준 (예: W07 = "지금은 신중 단계, 현금 40%"가 나온다)

### Phase 5: 정리

1. 팀원 종료 요청 (SendMessage) → 미응답 팀원은 TaskStop으로 정리
2. `_workspace/` 보존 (삭제 금지 — 다음 주차의 입력이자 감사 추적)
3. 사용자에게 보고: 완료 작업 / QA 결과(통과·실패·미검증) / P2 미착수 항목 / 다음 주차 제안
4. 피드백 기회 제공: 결과·팀 구성·워크플로우 개선점 질문

## 데이터 흐름

```
invest_develop_PLAN.md (원본 스펙)
        │
[리더] Agent 스폰(named, background) + TaskCreate
        │
data-engineer ──shape 계약──▶ quant-engineer ──스키마·상수──▶ llm-engineer
     │                             │                              │
     └──번들 API 스키마──────────────┴──────툴 정의·응답 shape──────▶ frontend-engineer
                                                                   │
각 모듈 완성 즉시 ──────────────▶ qa-inspector ──파일:라인 수정 요청──▶ 담당자
                                     │
                            _workspace/{week}_*_report.md
                                     │
                              [리더: 통합 보고]
```

## 에러 핸들링

| 상황 | 전략 |
|------|------|
| 팀원 1명 실패/중지 | SendMessage로 상태 확인 → 재시작. 재실패 시 작업을 리더가 직접 수행하거나 대체 팀원 생성 |
| KIS MCP 검색 실패 반복 | data-engineer가 파라미터 조합 변경 재시도 → 그래도 실패 시 해당 API는 "미해결"로 명세에 기록하고 진행 |
| 외부 API 키 미보유 (FRED/DART/KIS) | 수집기는 인터페이스+mock으로 완성, 실키 연동은 사용자에게 키 요청 후. 진행 보고서에 명시 |
| QA 실패 수정 루프 2회 초과 | 리더가 직접 원인 분석, 필요 시 사용자에게 스펙 확인 |
| 팀원 간 계약 충돌 (shape 불일치) | 생산자 명세(`_workspace/`)가 기준. 소비자가 맞추되, 명세가 플랜과 다르면 플랜 우선 |
| 안전 검증 실패 (주문 API 등) | **모든 작업 중단** 후 즉시 수정 — 다른 작업보다 우선 |

## 테스트 시나리오

### 정상 흐름 (W07 예시)
1. 사용자: "WEEK 07 매크로 엔진 개발 진행해줘"
2. Phase 0: `_workspace/`에 W06 산출물 존재 확인 → 이어서 실행
3. Phase 2: quant-engineer + qa-inspector 스폰(각 opus), 작업 5개 등록 (엔진 구현 → 오버라이드 → 신뢰도 → REGIME_PARAMS → 테스트, QA는 depends_on)
4. Phase 3: quant-engineer가 data-engineer의 W06 shape 명세를 읽고 구현, 완성 즉시 QA 요청
5. Phase 4: qa-inspector가 테스트 실행 + 판정 순서 확인 → 통과
6. Phase 5: 팀 정리, "지금은 신중 단계, 현금 40%" 데모 출력 보고

### 에러 흐름
1. W08에서 frontend-engineer가 번들 API 응답에 없는 필드 `valuation.label`에 접근
2. qa-inspector가 경계면 #1 교차 비교에서 발견 → data-engineer(생산자)·frontend-engineer(소비자) 양쪽에 SendMessage
3. 명세 확인 결과 생산자 명세가 기준 → frontend-engineer가 `valuation_label`로 수정
4. qa-inspector 재검증 통과 → 리더에게 리포트, 보고서에 이슈 이력 기록
