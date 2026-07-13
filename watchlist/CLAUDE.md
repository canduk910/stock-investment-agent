# watchlist/ — 관심종목(모듈 3) 백엔드

> 코드에서 자명하지 않은 결정·계약·함정만. 모듈 2(stock/) 분석 엔진을 **재사용**하고 신규 로직은 최소화한다("진입할까?" 방향).

## 국면 진입게이트(entry_signal)는 폐기 — 항목3
- 국면별 종목 진입신호(`entry_signal`)·`regime_gate` 소비는 "너무 보수적"이라 **삭제**됐다. 국면은 **현금비중만** 관리(매크로 대시보드가 표시)하고, 종목별 `single_cap`/`per_max`/`pbr_max` 커트로 신규진입을 판정하지 않는다.
- `_enrich_item` 에서 `entry_signal` 필드 제거, `regime` 블록은 `{regime}`(국면명)만. `judgement` 파라미터는 시그니처만 유지(호출측 계약 보존, 내부 미사용). 종목의 raw `per`/`pbr` 은 정량 데이터로 그대로 표시.

## 시세는 종목별 inquire_price 병렬 (multiprice 아님)
- `per`/`pbr`(정량 표시용)이 필요한데 `intstock_multprice`는 `price`/`change_rate`만 준다 → `collectors.kis.inquire_price`를 종목별 `ThreadPoolExecutor` 병렬(api/detail.py `_fetch_sections_parallel` 패턴)로 부른다.
- **현재가 캐시 금지(원칙1)**: store에 시세 필드를 저장하지 않는다. 시세는 매 조회 라이브. 시세 실패 종목은 값 `None` + `partial_failure`에 ticker 기록(번들 철학). `judgement=None`(매크로 실패) → `regime=None` + `partial_failure`에 `"regime"`(국면명 degraded).

## Store = durable 사용자 상태 (캐시 아님)
- `WatchlistStore` Protocol(`cache/base.py` 정신) + `JsonFileWatchlistStore`(`.cache/watchlist.json`, 원자적 write=temp+rename + `threading.Lock`) + `InMemoryWatchlistStore`(테스트).
- 키 `(user_id, ticker)` = DynamoDB PK/SK 계약(클라우드 전환 시 그대로 이관). `user_id` 기본 `DEFAULT_USER_ID="local"`(단일 로컬 사용자 — 프론트는 미전달). 파일은 `.cache/`에 두지만 **캐시 정책과 무관**(시세가 아닌 사용자 durable 데이터 → gitignore 대상).

## 계약·상수 (constants.py 단일 출처)
- **`SORT_KEYS`는 `chat/tools.py::show_watchlist` enum과 일치**(`registered`/`change_rate`/`near_target`) — 일치 테스트(`test_sort_keys_consistency.py`)로 3중 강제. 정렬 자체는 프론트 순수 로직(`watchlistLogic.js`)이 하고 백엔드는 `registered` 순으로 반환 + `sort_by` 에코.
- **`WATCHLIST_MAX_ITEMS=30`**: POST에서 **신규** 종목이 상한 도달이면 409(`watchlist full`)로 거부·미저장. 기존 ticker 갱신(upsert)은 개수를 안 늘리므로 허용(`existing is None`일 때만 상한 검사). KIS 레이트리밋·저장 폭주 방어.
- **`target_status`는 매수(진입가) 관점**: `current ≤ target`→`reached`(도달), `≤ target*(1+NEAR_TARGET_THRESHOLD_PCT%)`→`near`(근접), 그 외 `far`, target 없으면 `none`. `distance_to_target=(current-target)/target*100`. 프론트 `classifyTargetStatus`가 이 semantics를 복제한다(sell 관점으로 뒤집지 말 것).

## 스파크라인 시계열 (Phase D — `spark:number[]|null`)
- 각 item에 `spark` = 종목별 일봉 종가 시계열(최근 `WATCHLIST_SPARK_POINTS=20`개, **date 오름차순**). 프론트 미니차트 원천.
- 원천은 기존 일봉 어댑터 `chart.inquire_daily_itemchartprice`(FHKST03010100) 재사용 — **현재가 캐시 신설 금지(원칙1)**, 요청 시점 라이브 조회(캐시 배선 없음). 수정주가(`adj_price="0"`, 액면분할 갭 제거 → 추세 연속성). 룩백 `WATCHLIST_SPARK_LOOKBACK_DAYS=40`일(주말·공휴일 감안 20pt 확보).
- **선택적 시각화**: 시세(주 데이터)와 **독립 병렬** 조회(`_fetch_sparks_parallel`, 동시성 상한 공유). spark 실패·빈 candles·전량 종가결측 → `spark=None`(빈 리스트 아님). **spark 실패는 `partial_failure`를 오염시키지 않는다**(시세 실패 semantics 보존) — 시세 실패 종목도 spark는 독립 성공 가능. 종가 결측 candle은 제외(None 섞이면 프론트 스케일 깨짐).

## 서비스 반환 계약 (api/watchlist.py·프론트 WatchlistView 소비)
- `build_watchlist_view` → `{items:[{...저장필드, current_price, change_rate, per, pbr, distance_to_target, target_status, spark:number[]|null}], regime:{regime}|null, partial_failure:[ticker…/"regime"]}`. (진입신호 `entry_signal`·regime `single_cap`/`entry_blocked` 는 폐기 — 항목3.)
