# macro/ — 국면 판정 엔진 (규칙 기반, LLM 미개입)

> 코드에서 자명하지 않은 결정·계약만. 판정은 전부 결정적 순수 함수(dict→dict), LLM 절대 미개입.

## 2축 판정 (단일축 합산투표 아님 — 사용자 결정으로 재설계)
- 4지표를 **두 축으로 분리**: 경기(`yield_spread`+`hy_spread`, 신용·금리) × 심리(`vix`+`fear_greed`, 변동성·심리). 합치지 않는다.
- `score_axes` → `cycle_score`/`sentiment_score`(각 -2..+2). `classify(cs, ss)`가 **2×2(9셀)**로 국면 결정.
- **핵심 발산 규칙**: 경기 악화 + 심리 탐욕 → **과열**(위험한 고점) vs 경기 양호 + 심리 탐욕 → **확장**(건강). 심리만 보면 구분 불가 — 이게 2축 재설계의 이유.
- **회복은 2축에서 도달 가능**(경기 양호 + 심리 공포 = 저가매수 초입). 단일축 버전에선 회복 투표 규칙이 없어 도달 불가였다.

## 역발상 현금비중 (사용자 결정 — 방어적 아님)
- `REGIME_PARAMS.cash`: 회복 40 / 확장 60 / **과열 80**(고평가·탐욕→차익) / **수축 20**(급락·공포→매수). "쌀 때 사고 비쌀 때 판다".
- **단일 출처**: `recommended_cash_ratio`는 오직 `REGIME_PARAMS[regime]["cash"]`에서. 별도 `CASH_RATIO` 상수 **금지**(3중 일관성). 방어적↔역발상 전환은 이 4개 cash 숫자만 바꾼다.

## 함정·계약
- **VIX_PANIC(35)은 블랭킷 오버라이드가 아니다** — `vix_panic` 플래그만 세운다(UI 위험경고용). 심리축은 이미 vix>28을 공포로 반영하므로 판정 자체는 2축 로직이 결정. (기존 방어적 버전의 "무조건 수축 강제"는 폐기.)
- **누락 안전**: `score_axes`는 `data.get(k) is not None` 가드 — 키 부재(KeyError)와 present-but-None(TypeError) 둘 다 건너뛴다. `missing_indicators`에 기록, 임의 기본값 금지.
- **THRESHOLDS는 `score_axes` 로직과 1:1 일치**(표기용·W09 프롬프트 기준표 씨앗). 경계값(0/0.5, 5.0/3.0, 28/14, 25/75)은 전부 무투표(중립).
- **판정근거 노출(대시보드 카드·차트용)**: `_INDICATOR_SPEC`(지표별 axis·lo/hi·below/above·unit·source) + `classify_indicator(key, value)`(값→구간 양호/중립/악화·탐욕/중립/공포, 경계=중립) + `regime_breakdown(values)`(4지표 카드 리스트, 누락도 value/zone=None) + `indicator_meta(key)`(label/unit/source/axis/thresholds). **score_axes 부등호와 1:1(SSOT) — `test_classify_indicator_matches_score_axes`가 잠금**(둘 중 하나만 바꾸면 실패). `/api/macro/regime` 이 `indicator_breakdown` 으로 전개. 이건 국면 판정에 쓰인 **수치의 표면화**이지 새 판정이 아니다(판정은 여전히 score_axes/classify).
- `judge_regime` 반환 계약(api·frontend 소비): `regime`, `recommended_cash_ratio`, `confidence`(두 축 신호 유무: 둘 다→high/하나→medium/없음→low), `axes{cycle,sentiment: {score,sign}}`, `key_drivers[(label,axis,direction)]`, `params`, `vix_panic`, `missing_indicators`, `raw_data`. **`votes`·`override` 키는 없다**(단일축 잔재).
- `previous_regime` 파라미터는 시그니처만 유지·미사용(하이스테리시스 P2 dormant — 2축이 더 안정적이라 우선순위 낮음).

## 국면 이동 궤적(족적) — `regime_history.py`(순수 재현)
- **`build_trajectory(series_by_engine_key, exclude_month=None)`**: 과거 월별 지표 시계열을 **매 달 `judge_regime` 에 재현**해 `{date, cycle_score, sentiment_score, regime, recommended_cash_ratio, vix_panic, missing_indicators}` 리스트(시간 오름차순)를 낸다. **엔진이 순수·결정적이라 그대로 재사용**(라이브 판정과 동일 함수 → 임계값·현금비중 3중 일관성 자동). 이 모듈도 순수(수집·I/O 0) — 라우트가 수집한 월 시계열을 넘긴다.
- **부분 데이터 달 2중 배제**(매트릭스 점은 경기·심리 두 좌표가 다 있어야 의미): ① `exclude_month`(`YYYY-MM`) = **진행 중 당월**을 라우트가 KST 기준으로 넘겨 **결정적 제외**(FRED `frequency=m` 가 당월도 '경과일 평균'을 부분 관측치로 낼 수 있어, 그게 확정 과거값처럼 '현재' 점·캐시가 되는 걸 막는다 — FRED 의 당월 반환 타이밍에 의존하지 않음). ② `_CYCLE_KEYS`(yield_spread·hy_spread)·`_SENTIMENT_KEYS`(vix·fear_greed) **양축 결측 스킵**(과거 결측 달 방어 — 축 점수가 데이터 부족 탓에 0[중앙]으로 강제되는 아티팩트 방지). **공포탐욕(CNN) 결측이어도 심리축은 VIX 로 판정** → 궤적 유지.
- 라우트 `GET /api/macro/regime/history`(api/main.py)가 FRED 3 + 공포탐욕을 병렬 수집(`infra.parallel.fetch_parallel`) → `build_trajectory(exclude_month=당월)`. 확정 과거값이라 캐시(`macro:history:regime:`). 계약·graceful 은 `api/CLAUDE.md`.
