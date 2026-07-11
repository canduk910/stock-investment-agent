# Phase D 백엔드 — watchlist 스파크라인 (Task #20)

TDD Red→Green→Refactor. 전체 483 passed(이전 472 + spark 11), 10 deselected(live), 무회귀.

## 파일
- `watchlist/service.py` — spark 조회·추출·병합(chart 어댑터 재사용)
- `watchlist/constants.py` — `WATCHLIST_SPARK_POINTS=20`, `WATCHLIST_SPARK_LOOKBACK_DAYS=40`
- `watchlist/CLAUDE.md` — spark 계약 델타
- 테스트: `tests/unit/watchlist/test_service.py`(+9), `tests/unit/api/test_watchlist_route.py`(+2)

## 테스트 목록 → 구현 (test-first)

### 서비스 (test_service.py, 9케이스)
1. `test_spark_is_close_series` — 일봉 종가를 number[]로 노출
2. `test_spark_sorted_by_date_ascending` — KIS 최신순 입력도 date 오름차순 정렬(추세 뒤집힘 방지)
3. `test_spark_limited_to_recent_points` — N개 초과면 최근 N개(꼬리)만
4. `test_spark_none_on_chart_failure` — 일봉 실패→spark=None(graceful), 시세·진입신호 정상
5. `test_spark_none_on_empty_candles` — 빈 candles→None(빈 리스트 아님)
6. `test_spark_drops_none_closes` — 종가 결측 candle 제외(None 섞임 방지)
7. `test_spark_per_item_independent` — 한 종목 실패가 타 종목 spark 무영향
8. `test_spark_failure_not_in_partial_failure` — spark 실패는 partial_failure 미오염
9. `test_price_failure_still_attempts_spark` — 시세 실패 종목도 spark 독립 조회 성공

### 라우트 (test_watchlist_route.py, 2케이스)
10. `test_get_item_includes_spark` — GET item에 spark:number[]
11. `test_get_item_spark_null_on_chart_failure` — 일봉 실패→spark=null, partial_failure 미오염

## 구현 요지
- `chart.inquire_daily_itemchartprice`(FHKST03010100, 기존 MCP 검증 어댑터) **재사용** — 신규 KIS 코드 0.
- `_fetch_sparks_parallel`: 종목별 일봉 ThreadPool 병렬(시세와 **독립** 풀, `_worker_count` 동시성 상한 공유). `_spark_from_chart`: candles→date 오름차순 종가, None 제거, 최근 N개.
- **현재가 캐시 신설 금지(원칙1)**: 일봉을 요청 시점 라이브 조회(캐시 배선 없음). 수정주가(adj_price="0", 액면분할 갭 제거).
- per-item graceful: 예외/빈/전량결측 → spark=None. spark 실패는 partial_failure에 **안 넣음**(선택적 시각화 — 시세 실패 semantics 보존).

## 확정 계약 (frontend·qa 소비)
GET /api/watchlist item에 **`spark: number[] | null`** 추가:
- number[]: 일봉 종가 최근 20개, date 오름차순(가장 최신이 배열 끝). 종목마다 길이 다를 수 있음(≤20).
- null: 일봉 조회 실패 / candles 없음(신규상장) / 전량 종가결측. 프론트는 null이면 미니차트 미표시(빈 리스트 케이스 없음 — 렌더 분기 단순).
- spark 실패는 `partial_failure`에 나타나지 않음(시세 실패만 ticker 기록). regime 블록·기존 필드 전부 불변.

## 미해결/주의
- 시세 풀 + spark 풀이 순차 실행(각 내부는 병렬). 30종목·상한 6이면 왕복 2회분 지연 — 60s refresh·상한으로 허용 범위. 필요 시 단일 풀 통합 가능하나 코드 명료성(시세=주 데이터·partial_failure / spark=선택적) 위해 분리 유지.
- WATCHLIST_SPARK_LOOKBACK_DAYS=40일은 20영업일 확보용 여유. 장기 휴장 시 20개 미만 가능(그래도 유효 — 있는 만큼 표시).
