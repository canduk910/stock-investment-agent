# chat/ — LLM 계층 (설명만 하는 챗봇)

이 계층의 존재 이유: **판정·숫자는 코드가 확정하고, LLM은 그 결과를 설명만 한다.** 상세 규칙은 `llm-safety-guide` 스킬.

- **모델은 `CHAT_MODEL` 단일 출처**(`chat/tools.py`, 현재 `"gpt-5.4"`). 코드 어디에도 모델 문자열을 산재시키지 않는다 — 바꿀 땐 이 상수만.
- **risk_guardrail은 코드가 결정**한다. `intent.py`의 결정적 키워드 정규식(`guardrail_label`)이 ML보다 **먼저** 적용돼 차단하며, 차단 시 **LLM을 호출하지 않는다**(단정예측/내부정보/시세조종/과도위험 4유형 → 거절이 아니라 위험 환기 + 분산 안내로 방향 전환). 스트리밍 경로에서도 동일(라우트가 진입점에서 먼저 걸러 `live_judgement`도 미실행 → FRED 낭비 0).
- **인텐트 6분류 = ML 사전분류.** `intent_gen.py`가 gpt-5.4로 [질문→라벨] 균형 데이터(`data/intent_dataset.tsv`)를 생성 → `intent_train.py`가 `TfidfVectorizer(char_wb,(2,4))+LogisticRegression`으로 학습 → `chat/models/intent_clf.joblib`. 한글은 형태소분석기 없이 char n-gram으로 처리. 재생성/재학습해도 파이프라인 정의는 불변. **ML 정확도는 비결정적** → 단위 테스트는 인터페이스·가드레일만 고정하고 정확도는 단정하지 않는다. 비차단 라벨(general_qa↔stock_analysis 등) 오분류는 안전 무관(LLM이 tool_choice로 팝업 여부 결정).
- **기준표는 자동 생성**(`build_prompt.py::build_criteria_text`). `THRESHOLDS`·`INDICATOR_LABELS`·`VIX_PANIC`을 import해 만든다 — 임계값 숫자를 프롬프트에 하드코딩하면 3중 일관성이 깨진다. 시스템 프롬프트 필수 6블록(역할·판정출처고정·기준표+judgement·REGIME_PARAMS·설명지침·팝업규칙)과 면책 고지 포함. `judgement`는 매 호출 최신값 주입.
- **세션은 서버 인메모리**(`session.py`의 `SESSIONS[session_id]`, 슬라이딩 윈도우 8). 시스템 프롬프트는 매 호출 재주입(누적 X → 국면 변경 자동 반영), tool 메시지는 히스토리에 미누적. 휘발성(서버 재시작 시 손실 — 클라우드 전환 시 DynamoDB/Redis).
- **팝업은 tool_calls에서만** 생성된다(`chat.py`). LLM은 "무엇을 띄울지"만 결정하고 실데이터는 프론트가 직접 조회(환각 차단). tool 결과는 `{"ok":True}` 확인만 되먹인다. 반환 계약 `{text, popups:[{name,args}]}`.
- **스트리밍(`chat_stream`)**: SSE용 동기 제너레이터. 이벤트 `{type: "stage"|"token"|"popups"|"done"}`, stage enum = `analyze|regime|generate|summarize`. gpt-5.4 `stream=True`. **스트리밍 tool_calls는 델타 조각을 index별로 이어붙여 재조립**(`_accumulate_tool_calls`) — 부분 도착하는 `function.name`/`arguments`를 누적해야 완전한 팝업이 나온다. 기존 동기 `chat()`은 그대로 유지(논스트림 폴백·기존 테스트). OpenAI 실패는 1회 재시도 후 `_FALLBACK_MESSAGE`.
- 테스트는 OpenAI 클라이언트를 mock(스트리밍은 FakeClient가 델타 청크 yield), ML은 소형 시드 fixture(`tests/fixtures/intent_seed.tsv`)로 학습해 라이브 호출 없이 검증.
- **[P2] 구조화 리포트(§6.5b)**: `report_schema.py`의 `StockReport`(Pydantic)가 안전 요건을 **스키마 레벨에서 강제** — `리스크요인 min_length=1`(장밋빛 일변도 방지)·`면책고지` 필수·`종합의견 Literal["긍정적","중립","신중"]`(매수/매도 단정 라벨 원천 차단). `report.py::generate_stock_report`는 `CHAT_MODEL`로 JSON 생성 → 검증 실패 1회 재시도 → 재실패 시 **폴백**(정량요약만 + `validation_failed=True`, 부분실패 보존, §5.1). `report_store.py`가 `.cache/stock_reports.json`에 `(ticker, created_at)`·`regime_at_creation`으로 히스토리 누적(과거 평가 비교 데모). 테스트는 FakeOpenAI mock(라이브 미호출).
- **진입신호 지침(build_prompt)**: 시스템 프롬프트에 "관심종목 진입 신호는 `single_cap>0` **그리고** `per_max`/`pbr_max` 이내일 때만 '검토 가능'; `single_cap=0` 국면은 신규진입 미제안" 블록 추가. **숫자 하드코딩 0** — 이미 주입된 `REGIME_PARAMS`에서 파생(3중 일관성). 관심종목 진입 판정은 `watchlist/` 코드가, LLM은 서술만.
