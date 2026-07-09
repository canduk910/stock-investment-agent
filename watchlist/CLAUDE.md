# watchlist/ — 관심종목(모듈 3) 백엔드

> 코드에서 자명하지 않은 결정·계약·함정만. 모듈 2(stock/) 분석 엔진을 **재사용**하고 신규 로직은 최소화한다("진입할까?" 방향).

## 진입신호 = regime_gate 재사용 (재구현 금지)
- 종목별 진입신호는 `stock.summary.regime_gate(valuation, judgement)`를 그대로 쓴다. 임계값·게이트 로직을 여기서 다시 만들지 않는다.
- **regime-agnostic**: 엔진이 계산한 `single_cap`/`entry_blocked`를 **소비만** 한다 — 국면명(`"과열"` 등)을 하드코딩하지 않는다. 역발상 모델에서 신규진입 억제 국면은 **과열(`single_cap=0`→`per_max=None`→`entry_blocked`)**이다. (로드맵 문구 "수축 `single_cap=0`"은 W07 역발상 전환 전 잔재 — 엔진 값 소비로 자동 해소.)
- `entry_signal.entry_allowed = not entry_blocked and not per_over and not pbr_over`. `note`는 사실 서술만(매수/매도 명령형 금지).

## 시세는 종목별 inquire_price 병렬 (multiprice 아님)
- 진입 게이트에 `per`/`pbr`이 필요한데 `intstock_multprice`는 `price`/`change_rate`만 준다 → `collectors.kis.inquire_price`를 종목별 `ThreadPoolExecutor` 병렬(api/detail.py `_fetch_sections_parallel` 패턴)로 부른다.
- **현재가 캐시 금지(원칙1)**: store에 시세 필드를 저장하지 않는다. 시세는 매 조회 라이브. 시세 실패 종목은 값 `None` + `partial_failure`에 ticker 기록(번들 철학). `judgement=None`(매크로 실패) → 종목별 `entry_signal=None` + `partial_failure`에 `"regime"`.

## Store = durable 사용자 상태 (캐시 아님)
- `WatchlistStore` Protocol(`cache/base.py` 정신) + `JsonFileWatchlistStore`(`.cache/watchlist.json`, 원자적 write=temp+rename + `threading.Lock`) + `InMemoryWatchlistStore`(테스트).
- 키 `(user_id, ticker)` = DynamoDB PK/SK 계약(클라우드 전환 시 그대로 이관). `user_id` 기본 `DEFAULT_USER_ID="local"`(단일 로컬 사용자 — 프론트는 미전달). 파일은 `.cache/`에 두지만 **캐시 정책과 무관**(시세가 아닌 사용자 durable 데이터 → gitignore 대상).

## 계약·상수 (constants.py 단일 출처)
- **`SORT_KEYS`는 `chat/tools.py::show_watchlist` enum과 일치**(`registered`/`change_rate`/`near_target`) — 일치 테스트(`test_sort_keys_consistency.py`)로 3중 강제. 정렬 자체는 프론트 순수 로직(`watchlistLogic.js`)이 하고 백엔드는 `registered` 순으로 반환 + `sort_by` 에코.
- **`WATCHLIST_MAX_ITEMS=30`**: POST에서 **신규** 종목이 상한 도달이면 409(`watchlist full`)로 거부·미저장. 기존 ticker 갱신(upsert)은 개수를 안 늘리므로 허용(`existing is None`일 때만 상한 검사). KIS 레이트리밋·저장 폭주 방어.
- **`target_status`는 매수(진입가) 관점**: `current ≤ target`→`reached`(도달), `≤ target*(1+NEAR_TARGET_THRESHOLD_PCT%)`→`near`(근접), 그 외 `far`, target 없으면 `none`. `distance_to_target=(current-target)/target*100`. 프론트 `classifyTargetStatus`가 이 semantics를 복제한다(sell 관점으로 뒤집지 말 것).

## 서비스 반환 계약 (api/watchlist.py·프론트 WatchlistView 소비)
- `build_watchlist_view` → `{items:[{...저장필드, current_price, change_rate, per, pbr, distance_to_target, target_status, entry_signal:{entry_blocked, per_over, pbr_over, single_cap, entry_allowed, note}}], regime:{regime, single_cap, entry_blocked}, partial_failure:[ticker…/"regime"]}`.
