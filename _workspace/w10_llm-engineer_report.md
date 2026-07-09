# W10 llm-engineer — 진입신호 프롬프트(3중 일관성) + P2 Pydantic 리포트

담당 Task #6·#7·#8. TDD Red→Green→Refactor. LLM 출력은 비결정적이라 대상 아님 —
그 주변의 결정적 코드(프롬프트 상수 파생·Pydantic 안전필드·생성 폴백·라우트 계약)만 테스트.
**"테스트 목록(스펙 근거) → 구현" 순서**로 기록(qa test-first 증거).

---

## Task #6 — chat/build_prompt.py 진입신호 지침 (3중 일관성)

### 테스트 목록 (Red 먼저 — tests/unit/chat/test_build_prompt.py 추가분)
- `test_prompt_contains_entry_signal_guidance_block` — 진입신호 지침 블록 존재("진입"·"single_cap"·"per_max"·"pbr_max"·"검토 가능"). Red: 마커 없어 assertion 실패 확인.
- `test_entry_signal_guidance_is_regime_agnostic__no_hardcoded_numbers` — **핵심 3중 일관성 회귀**: 과열(single_cap=0) vs 회복(single_cap>0) 두 국면에서 진입신호 지침 '문구'가 동일해야 함(국면별 숫자는 이미 ④ REGIME_PARAMS 주입 블록에서만 나옴). `_extract_entry_guidance()`로 지침 블록만 잘라 비교.
- `test_entry_signal_guidance_has_no_hardcoded_regime_param_values` — 지침 문구에 REGIME_PARAMS 구체값(per_max=15/20, pbr_max=1.5/2.0)이 타이핑돼 있지 않음. `single_cap>0`은 부등호 서술이라 허용, 특정 상한값은 금지.

### 구현 (Green)
- `build_prompt()`에 ⑤ [관심종목 진입 신호 — 서술 규칙] 블록 추가. 기존 ⑤(설명지침)→⑥, ⑥(팝업규칙)→⑦로 번호 재배치.
- 문구는 **변수명(single_cap/per_max/pbr_max)만 참조**, 숫자 하드코딩 0. 규칙: single_cap>0 AND per_max·pbr_max 이내 → "검토 가능"(사실 서술, 매수 권유 아님) / single_cap=0 → 신규진입 미제안(관찰 대상). 명령형·확정형 금지 문장 포함.
- 실제 국면별 숫자는 이미 주입되던 ④ `_format_params(regime)` 블록에서 파생(단일 출처 유지).

---

## Task #7 — chat/report_schema.py StockReport Pydantic

### 테스트 목록 (Red 먼저 — tests/unit/chat/test_report_schema.py, 17개)
- 정상 통과 / 종합의견 3값(긍정적·중립·신중) 각각 통과.
- **종합의견 enum**: "매수","매도","적극매수","강력추천","positive" → ValidationError(명령형 라벨 원천 배제).
- **리스크요인 min_length=1**: `[]` → ValidationError(장밋빛 방지). 4개 → ValidationError(max_length=3).
- **투자포인트 max_length=3**: 4개 → ValidationError. `[]`는 허용(min 제약 없음).
- **필수 필드**: 면책고지·요약·국면정합성 누락 → ValidationError.
- 직렬화: model_dump()가 한글 6키 그대로 반환(프론트·store 계약).

### 구현 (Green)
```python
class StockReport(BaseModel):
    종합의견: Literal["긍정적", "중립", "신중"]
    요약: str
    투자포인트: list[str] = Field(default_factory=list, max_length=3)
    리스크요인: list[str] = Field(min_length=1, max_length=3)   # 최소1 강제
    국면정합성: str
    면책고지: str                                                # 필수
```
- `OPINION_VALUES = ("긍정적","중립","신중")` — 프론트 reportFormat 배지 매핑과 일치할 SSOT.

---

## Task #8 — 생성·검증·폴백 + 히스토리 + 라우트

### chat/report_store.py (tests/unit/chat/test_report_store.py, 6개)
테스트: append→list_history 되읽기(created_at·regime_at_creation·report_json), ticker 격리,
누적 시 created_at 내림차순(최신 우선), 재오픈 지속성(tmp_path), 빈 히스토리, created_at 자동생성.
구현: `JsonFileReportStore` — watchlist/store.py와 동일 패턴(원자적 write=temp+os.replace, threading.Lock).
디스크 `{ticker: [{created_at, regime_at_creation, report_json}]}`. `append(ticker, report_json, *, regime_at_creation, created_at=None)`, `list_history(ticker)`(내림차순).

### chat/report.py (tests/unit/chat/test_report_generate.py, 8개)
테스트(FakeOpenAI mock): 정상 JSON→검증통과·validation_failed=False / CHAT_MODEL 단일출처 호출 /
성공 시 quant_summary 동봉 / 불량→1재요청→정상이면 회복(calls==2) / 2회 다 불량→폴백 /
깨진 JSON→폴백 / 종합의견 "매수"→폴백 / OpenAI 예외→폴백(크래시 없음).
구현: `generate_stock_report(bundle, judgement, *, client=None)`:
- `_build_report_prompt`: 정량요약·국면게이트를 근거로 JSON 서술만 지시(build_criteria_text 재사용, 재판정·숫자생성 금지, 단정 금지, 면책 필수).
- `response_format={"type":"json_object"}` + CHAT_MODEL. 파싱+StockReport 검증. 실패 시 1회 재요청(총 2회 루프) → 폴백.

### api/report.py (tests/unit/api/test_report_route.py, 6개 — 로컬 FastAPI 앱)
테스트(경계 monkeypatch: _build_kis_client·_build_judgement·collect_stock_bundle·generate·_STORE):
POST 생성+저장(regime_at_creation) / created_at 반환 / 폴백은 저장 안 함·200 유지 /
judgement 실패해도 진행(regime_at_creation=None) / GET history 반환 / 빈 history.
구현: `router` — api/detail.py 자산 재사용(사이클 없음). 검증 통과분만 store.append.

---

## 응답 shape (프론트·QA 계약)

### POST /api/detail/{ticker}/report — 항상 200
```json
{
  "ticker": "005930",
  "report": { "종합의견":"긍정적|중립|신중", "요약":"", "투자포인트":["≤3"],
              "리스크요인":["≥1,≤3"], "국면정합성":"", "면책고지":"" } | null,
  "validation_failed": false,          // true면 report=null
  "quant_summary": { ... },            // bundle.summary (폴백에도 남음)
  "message": null | "AI 서술 생성 실패 ...",
  "regime_at_creation": "확장" | null, // 국면 수집 실패 시 null
  "created_at": "ISO8601"
}
```
### GET /api/detail/{ticker}/report/history
```json
{ "ticker": "005930",
  "history": [ { "created_at":"", "regime_at_creation":"과열", "report_json":{6필드} } ] }
```
history = created_at 내림차순(최신 우선). 빈 종목 → `history: []`.

---

## main.py 배선 (리더 전담 — 미편집)
```python
from api.report import router as report_router
app.include_router(report_router)
```
CORS는 GET/POST만 → 기존 설정 충분(DELETE/PATCH는 watchlist용).

## 검증
`uv run pytest tests/unit/chat tests/unit/api/test_report_route.py -q` → **94 passed**.
전체(-m "not live") 400 passed / 1 failed — 실패는 test_watchlist_route(data-engineer T3) 소관, 내 작업 무관.

## 안전 요건 이행 (§10)
- 주문 API 0(조회+서술 생성만). 종합의견 매수/매도 타입 배제. 리스크 min1·면책 필수(스키마 강제).
- 진입신호 지침 숫자 하드코딩 0(REGIME_PARAMS 파생, 국면-agnostic). 폴백 부분실패 보존(quant_summary 유지, 폴백 미저장). 라이브 미호출(FakeOpenAI mock).
