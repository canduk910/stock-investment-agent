# api/ — 로컬 백엔드 (FastAPI)

- 이 앱은 **AWS Lambda + API Gateway의 로컬 스탠드인**이다(로컬 우선 결정). 여기서 정의한 **엔드포인트 계약을 React 프론트가 그대로 소비**하고, 배포 시 Lambda 핸들러로 옮긴다 — 그래서 계약을 함부로 바꾸지 않는다.
- **현재값은 매 요청마다 실시간 수집**한다(캐시 미경유, 원칙1).
- `GET /api/macro/indicators` → `{indicators: {key: IndicatorPoint|null}, partial_failure: [key]}`. `IndicatorPoint`의 `as_of(date)`는 FastAPI 인코더가 ISO 문자열로 직렬화한다.
- `GET /api/macro/regime` → `{...judgement, indicators_used, partial_failure}`. `judgement`는 `macro.engine.judge_regime`의 반환 계약(2축: regime/recommended_cash_ratio/confidence/axes/key_drivers/params/vix_panic/missing_indicators/raw_data — 구 `votes`·`override`는 `axes`·`vix_panic`으로 대체·폐기). `axes`는 `{cycle:{score,sign}, sentiment:{score,sign}}`, `key_drivers` 원소는 `(label, axis, direction)` tuple, `vix_panic`은 `vix>35` 표시 플래그(블랭킷 오버라이드 아님). 흐름: `collect_macro_indicators`로 실시간 수집(캐시 미경유) → 국면 4지표(`t10y2y→yield_spread`/`hy_spread`/`vix`/`fear_greed`)만 `.value` 추출해 엔진 입력 dict 구성(None·부분실패·키부재는 제외, 임의 기본값 금지) → `judge_regime` 호출. `indicators_used`=엔진에 실제 넣은 `{엔진키: value}`, `partial_failure`=국면 4지표 중 못 쓴 엔진키. `dollar_index·gdp`는 수집돼도 판정 제외(매핑은 `_REGIME_INPUT_MAP` 단일 출처). `key_drivers`의 tuple 은 JSON 배열로 직렬화된다. 판정은 전부 규칙 코드(LLM 미개입).
- CORS는 Vite 개발 서버(`localhost:5173`)만 허용. 프론트는 실제로 Vite 프록시로 호출하므로 CORS는 보조 안전망.
- 테스트는 `collect_macro_indicators`·`fred_api_key`를 경계로 mock → 실 API/키 없이 계약 검증(`tests/unit/api/`).
