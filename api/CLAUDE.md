# api/ — 로컬 백엔드 (FastAPI)

- 이 앱은 **AWS Lambda + API Gateway의 로컬 스탠드인**이다(로컬 우선 결정). 여기서 정의한 **엔드포인트 계약을 React 프론트가 그대로 소비**하고, 배포 시 Lambda 핸들러로 옮긴다 — 그래서 계약을 함부로 바꾸지 않는다.
- **현재값은 매 요청마다 실시간 수집**한다(캐시 미경유, 원칙1).
- `GET /api/macro/indicators` → `{indicators: {key: IndicatorPoint|null}, partial_failure: [key]}`. `IndicatorPoint`의 `as_of(date)`는 FastAPI 인코더가 ISO 문자열로 직렬화한다.
- CORS는 Vite 개발 서버(`localhost:5173`)만 허용. 프론트는 실제로 Vite 프록시로 호출하므로 CORS는 보조 안전망.
- 테스트는 `collect_macro_indicators`·`fred_api_key`를 경계로 mock → 실 API/키 없이 계약 검증(`tests/unit/api/`).
