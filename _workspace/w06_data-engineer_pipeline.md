# WEEK 06 — 데이터 파이프라인 구현 명세 (data-engineer)

TDD로 T1~T10을 Red→Green→Refactor로 구현했다. 아래는 **테스트 목록(스펙 근거) → 구현**
순서와, 소비자(quant-engineer / frontend-engineer)를 위한 **정규화 반환 shape 계약**이다.

- 실행: `uv run pytest -q` → **58 passed** (기본 -m 'not live'), live 4건은 `-m live`로 분리.
- KIS 6개 함수 + 업종지수 1개 전부 `kis-code-assistant` MCP로 실제 코드 검증 후 어댑터화(기억 작성 없음).
- 매매 주문(order/buy/sell) 계열: 검색·구현 모두 없음. 안전 grep 통과.

---

## 1. 테스트 목록 (스펙 근거) → 구현

### T1 캐시 레이어 (원칙 3원칙 구조 강제)
| 테스트 (스펙 근거) | 검증 | 구현 |
|---|---|---|
| `test_price_key_rejected_by_policy__plan_7_1` | 현재가 프리픽스(stock:price:) 거부 | `cache/policy.py::is_cacheable` 화이트리스트 |
| `test_meta/macro/token_key_allowed_by_policy__plan_7_1` | 허용 프리픽스 통과 | `ALLOWED_PREFIXES` |
| `test_unknown_prefix_rejected__plan_7_1` | 미허용 프리픽스 거부 | 〃 |
| `test_partial_failure_present_skips_cache_set__plan_7_2` | 실패 응답 저장 생략 | `cache_if_clean` |
| `test_clean_response_is_cached__plan_7_2` | 정상 응답 저장 | 〃 |
| `test_cache_if_clean_rejects_forbidden_key__plan_7_1` | 이중 방어 | 〃 |
| `test_local_cache_ttl_expiry` / `test_file_cache_persists_*` | TTL 만료 / 토큰 영속 | `cache/local.py` LocalCache·FileCache |
| `test_macro/stock_meta/kis_token_key` | 키 컨벤션 | `cache/keys.py` |

### T2 KIS 인증 + 클라이언트
| 테스트 | 검증 | 구현 |
|---|---|---|
| `test_request_token_normalizes_and_computes_expiry` | 응답 정규화 + expires_at(epoch) | `collectors/kis/auth.py::request_token` |
| `test_token_refreshed_when_absent` | 미존재 시 발급·저장 | `auth.get_token` |
| `test_token_reused_when_not_near_expiry` | 만료 여유 시 재사용(HTTP 미호출) | 〃 (KIS 차단 방지) |
| `test_token_refreshed_when_near_expiry` | 만료 <1h 시 재발급 | `REFRESH_MARGIN_SECONDS=3600` |
| `test_get_injects_auth_headers_and_returns_json` | authorization/appkey/appsecret/tr_id/custtype 주입 | `client.py::KisClient.get` |
| `test_real/demo_env_uses_*_domain` | env별 도메인 분기 | `KIS_DOMAINS` |

### T3 조회 어댑터 5종 + normalize
| 테스트 | 검증 | 구현 |
|---|---|---|
| `test_to_float/int_*`, `test_missing_field_returns_none` | 부호·콤마 코어스 / KeyError 금지 | `normalize.py::to_float/to_int/pick` |
| `test_normalize_balance/quote/daily_chart/multiprice/stock_info_shape` | 정규화 계약 | `normalize.normalize_*` |
| `test_inquire_balance_returns_normalized` / `_demo_tr_id` | 어댑터+env별 TR_ID | `balance.py` |
| `test_quote/daily_chart/multiprice/stock_info_returns_normalized` | 어댑터 파라미터·정규화 | `quote/chart/multiprice/stock_info.py` |
| `test_current_price_adapters_have_no_cache_param__plan_7_1` | 현재가 어댑터 cache 인자 부재 | 시그니처 강제 |

### T4 섹터 업종지수
| 테스트 | 검증 | 구현 |
|---|---|---|
| `test_normalize_sector_index_shape` | 지수 정규화 | `normalize.normalize_sector_index` |
| `test_sector_index_adapter` | TR_ID/파라미터 | `sector_index.py` |

### T5-T7 외부 지표
| 테스트 | 검증 | 구현 |
|---|---|---|
| `test_fetch_fred_series_picks_latest_non_nan` | 결측('.') 건너뛰고 최신 유효값 | `fred.py::fetch_fred_series` |
| `test_fetch_t10y2y_wrapper_uses_series_id`, `test_fred_wrappers_series_ids` | series_id 매핑 | `fetch_t10y2y/hy_spread/dollar_index/gdp` |
| `test_vix_from_yahoo_primary` | 야후 1차 | `vix.py::fetch_vix` |
| `test_vix_falls_back_to_fred_when_yahoo_fails` | FRED VIXCLS 폴백 + source 기록 | 〃 |
| `test_fear_greed_success` | IndicatorPoint 반환 | `fear_greed.py::fetch_fear_greed` |
| `test_fear_greed_failure_returns_none_without_raising` | graceful(None, 예외 미전파) | 〃 |

### T8 캐시 통합 배선
| 테스트 | 검증 | 구현 |
|---|---|---|
| `test_stock_meta_fetched_then_cached_then_reused` | fetch→저장→재사용 | `cache/service.py::get_or_fetch` |
| `test_macro_indicator_cached_via_policy` | 매크로 캐시 경유 | 〃 |
| `test_partial_failure_not_cached__plan_7_2` | 실패 응답 미저장(재시도) | 〃 (cache_if_clean 경유) |
| `test_current_price_path_never_calls_cache_set__plan_7_1` | 현재가 경로 cache.set 부재 | 어댑터에 캐시 미배선 |

### T9 live 스모크 (`@pytest.mark.live`, 기본 실행 제외)
`test_live_kis_balance / fred_t10y2y / vix / fear_greed` — 키 없으면 skip. `uv run pytest -m live`.

---

## 2. 정규화 반환 shape 계약 (소비자용)

### KIS 어댑터 (`collectors/kis/`)
```
inquire_balance(client, cano, acnt_prdt_cd) -> {
  "holdings": [ {ticker:str, name:str, qty:int, avg_price:float, current_price:float,
                 eval_amount:float, pnl_amount:float, pnl_pct:float} ],
  "summary": {deposit:float, purchase_amount:float, eval_amount:float,
              pnl_amount:float, total_eval:float, net_asset:float}
}   # 현재가 포함 → 캐시 금지

inquire_asking_price_exp_ccn(client, ticker, market="J") -> {
  ticker:str, price:float, change_rate:float, ask:float, bid:float, as_of:str(HHMMSS)
}   # 캐시 금지(원칙1). change_rate = antc_cntg_prdy_ctrt(예상체결 전일대비율)

inquire_daily_itemchartprice(client, ticker, start_date, end_date, period="D", adj_price="1") -> {
  ticker:str, candles:[ {date:'YYYYMMDD', open:float, high:float, low:float, close:float, volume:int} ]
}   # 일봉(확정 과거) → 조건부 캐시 가능

intstock_multprice(client, tickers:list[str], market="J") -> {
  items:[ {ticker:str, price:float, change_rate:float} ]
}   # 현재가 → 캐시 금지. 최대 30종목

search_stock_info(client, ticker) -> {
  ticker:str, name:str, sector:str, listed_shares:int,
  capital:float, par_value:float, security_group:str
}   # 메타 → stock:meta:{ticker} 캐시 허용

sector_index.inquire_index_price(client, index_code) -> {
  index_code:str, price:float, change:float, change_rate:float, volume:int,
  advancing:int, declining:int, unchanged:int
}   # 지수 현재가 실시간 → 캐시 금지. index_code 예: 0001 코스피, 1001 코스닥, 2001 코스피200
```

### 외부 지표 (`collectors/`) — 공통 IndicatorPoint
```
IndicatorPoint = {key:str, value:float, as_of:datetime.date, source:str, prev_value:float|None}

fred.fetch_t10y2y/hy_spread/dollar_index/gdp(api_key)  # source="FRED", series_id별
vix.fetch_vix(fred_api_key)                            # source="yahoo"|"fred"
fear_greed.fetch_fear_greed()                          # 성공 IndicatorPoint(source="CNN") | 실패 None
```
- `value`는 항상 float, `as_of`는 `datetime.date`. `prev_value`는 [P2] 모멘텀 확장 훅(FRED만 채움).
- 공포탐욕은 **None을 반환할 수 있다** — 소비자(번들/대시보드)는 None을 partial_failure로 기록할 것.

### 캐시 (`cache/`)
```
service.get_or_fetch(cache, key, fetch, ttl_seconds)   # 메타/매크로 캐시 경유(정책 강제)
policy.is_cacheable(key)                                # 허용: macro:/stock:meta:/kis:token:  그 외 CachePolicyError
policy.cache_if_clean(cache, key, value, ttl)           # value["partial_failure"] 비었을 때만 set
keys.macro_key / stock_meta_key / kis_token_key
```
- KIS 인증 토큰: `auth.get_token(config, cache)` — FileCache(`kis:token:{env}`)에 저장, 만료 <1h만 재발급.

---

## 3. TR_ID / PATH 참조표 (MCP 검증)

| 어댑터 | TR_ID | PATH |
|---|---|---|
| auth_token | — (POST) | `/oauth2/tokenP` |
| inquire_balance | TTTC8434R(real)/VTTC8434R(demo) | `/uapi/domestic-stock/v1/trading/inquire-balance` |
| inquire_asking_price_exp_ccn | FHKST01010200 | `/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn` |
| inquire_daily_itemchartprice | FHKST03010100 | `/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice` |
| intstock_multprice | FHKST11300006 | `/uapi/domestic-stock/v1/quotations/intstock-multprice` |
| search_stock_info | CTPF1002R | `/uapi/domestic-stock/v1/quotations/search-stock-info` |
| inquire_index_price | FHPUP02100000 | `/uapi/domestic-stock/v1/quotations/inquire-index-price` |

도메인: real `https://openapi.koreainvestment.com:9443` / demo `https://openapivts.koreainvestment.com:29443`.

---

## 4. 라이브 확정 완료 / 잔여 항목

- **intstock_multprice output 필드 — ✅ 라이브 확정(해소)**: 실 KIS 응답으로 필드명
  확정 — `inter_shrn_iscd`(종목코드) / `inter2_prpr`(현재가) / `prdy_ctrt`(전일대비율).
  1차 후보키가 정답이었고 2차 추정키(`mksc_shrn_iscd`/`stck_prpr`)는 실재하지 않아
  `normalize_multiprice`에서 제거함(죽은 분기 정리). fixture는 이미 실필드명 기준이라
  변경 불필요. graceful(필드 부재→None) 견고성 테스트만 유지
  (`test_normalize_multiprice_missing_fields_are_graceful`). 라이브 게이트
  `test_live_kis_multiprice_confirms_field_mapping` 통과로 계약 확정.
- **quote change_rate**: inquire_asking_price_exp_ccn은 실시간 현재가 등락률 필드가 없어
  `antc_cntg_prdy_ctrt`(예상체결 전일대비율)를 사용. 정확한 현재가 등락률이 필요하면
  W08에서 별도 현재가 API(FHKST01010100) 추가 검토.

## 5. QA 참고
- `fear_and_greed`는 import 시 `requests_cache`를 전역 설치해 다른 테스트의 `responses`
  mock을 오염시킴 → `collectors/fear_greed.py`에서 **지연 import**로 격리(모듈 top-level import 없음).
- 안전 grep 전부 통과: 주문 함수 부재 / 키 하드코딩 부재 / 현재가 어댑터 cache 미배선.
