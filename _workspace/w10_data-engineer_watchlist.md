# W10 data-engineer — 워치리스트 백엔드 (T1·T2·T3)

TDD Red→Green→Refactor. 전체 회귀 401 passed(기존 281 → 워치리스트 80 추가), 9 deselected(live).

## 파일

| 구분 | 파일 |
|------|------|
| 상수 | `watchlist/constants.py` |
| 모델 | `watchlist/models.py` |
| 저장소 | `watchlist/store.py` |
| 서비스 | `watchlist/service.py` |
| 라우트 | `api/watchlist.py` |
| 테스트 | `tests/unit/watchlist/{test_models,test_store,test_sort_keys_consistency,test_service}.py`, `tests/unit/api/test_watchlist_route.py` |

## T1 — 저장·모델·상수 (테스트 목록 → 구현)

### Red (test_models.py 8케이스)
- valid ticker(005930/A12345/abc123) 수용, invalid(00593/삼성전자/공백) 거부 → `^[0-9A-Za-z]{6}$`
- target_price 음수 거부(ge=0), 0·양수 수용, None 기본
- reason 옵션(None 기본), user_id 기본 "local", model_dump round-trip

### Red (test_store.py — memory·file 두 구현 parametrize, 원자성 file 전용)
- 빈 목록, get missing=None, put→get, put→list, delete, delete missing=noop
- **upsert: 중복 추가=갱신하되 added_at 최초 보존**
- update_target(반환·조회 반영·added_at 보존·missing=None)
- **(user_id,ticker) 격리**(한 사용자 삭제가 타 사용자 무영향), 같은 ticker 다른 user 공존
- list 등록순(added_at 오름차순)
- file: 재오픈 지속성, 부재 파일=빈, **손상 파일=빈(예외 전파 금지)**, temp 잔여 없음(원자적), 디스크 유효 JSON

### Red (test_sort_keys_consistency.py 2케이스)
- `SORT_KEYS == chat/tools.py show_watchlist enum`(런타임 TOOLS 추출, 하드코딩 회피)
- 고정값 `["registered","change_rate","near_target"]`

### Green
- `constants.py`: SORT_KEYS, DEFAULT_USER_ID="local", WATCHLIST_MAX_ITEMS=30, NEAR_TARGET_THRESHOLD_PCT=3.0, WATCHLIST_STORE_PATH=".cache/watchlist.json"
- `models.py`: `WatchlistItem(BaseModel)` — user_id/ticker(pattern)/stock_name/reason/target_price(ge=0)/added_at. `TICKER_PATTERN` export.
- `store.py`: `WatchlistStore` Protocol + `InMemoryWatchlistStore` + `JsonFileWatchlistStore`(원자적 temp+`os.replace`, `threading.Lock`, upsert=added_at 보존). 내부 저장 형태 `{user_id: {ticker: item_dict}}`.

## T2 — 서비스·진입신호 (test_service.py 15케이스)

### Red 핵심(regime-agnostic 회귀)
- 반환 고정키 {items, regime, partial_failure}, regime 블록 {regime, single_cap, entry_blocked}
- 저장 필드 + 라이브 시세(current_price/change_rate/per/pbr) 병합, 등록순 정렬
- **entry_signal = regime_gate 파생**: 수축(single_cap=5, per_max=20)→미차단·per_over 판정 / **과열(single_cap=0, per_max=None)→entry_blocked True(밸류에이션 무관)**
- **regime-agnostic**: 같은 종목이 국면만 바꿔도 엔진 single_cap 따라감(국면명 하드코딩 0)
- distance_to_target=(current-target)/target*100, target_status {reached(≤target)/near(≤target*(1+3%))/far/none}
- **부분실패**: 시세 실패 종목 값 None + entry_signal None + partial_failure에 ticker(나머지 정상, 저장필드 유지)
- **judgement=None → 모든 entry_signal None + regime None + partial_failure에 "regime"**(시세는 정상)

### Green
- `service.py::build_watchlist_view(store, user_id, kis_client, judgement)`. 종목별 `inquire_price.inquire_price` 병렬(ThreadPoolExecutor, api/detail 패턴). `regime_gate(valuation, judgement)` 소비. regime 블록 entry_blocked도 `params.per_max is None`만 소비(regime_gate와 동일 규칙, 국면명 미참조).

## T3 — CRUD 라우트 (test_watchlist_route.py 15케이스)

로컬 앱(`FastAPI()+include_router`)으로 테스트. 경계 monkeypatch: `_get_store`·`_build_kis_client`·`_build_judgement`·`service.inquire_price.inquire_price`·`_resolve_stock_name`.

### Red
- GET: 빈(sort_by 기본 registered), enriched, sort_by 에코, **enum밖 sort_by→registered 폴백(500 아님)**, judgement 실패→regime None+partial "regime"(시세 정상)
- POST: 추가(ok,item,added_at), **stock_name 없으면 _resolve_stock_name**, **불량 ticker→400(저장 안 함)**, upsert added_at 보존
- DELETE: 제거, missing=ok(idempotent)
- PATCH: 목표가 갱신, **missing→404**, **음수→422(Pydantic ge=0)**
- user_id 격리(쿼리)

### Green
- `api/watchlist.py`: 4 라우트. `_build_kis_client`·`_build_judgement`는 **api.detail에서 import**(순환 회피, api.main 미참조 — 검증 완료). 싱글톤 `JsonFileWatchlistStore(.cache/watchlist.json)`. AddRequest/PatchRequest Pydantic(target_price ge=0). ticker는 라우트에서 명시 400 검증(target 음수 422와 구분). `_resolve_stock_name`=마스터 exact match→inquire_price→ticker 폴백(실패해도 추가 성공).

## 확정 계약 (frontend·qa 소비)

```
GET /api/watchlist?sort_by=&user_id= →
{
  items: [{
    user_id, ticker, stock_name, reason, target_price, added_at,
    current_price, change_rate, per, pbr,
    distance_to_target,               // (current-target)/target*100 또는 null
    target_status,                    // "reached"|"near"|"far"|"none"
    entry_signal: {                   // 시세/판정 실패 시 null
      entry_blocked, per_over, pbr_over, single_cap, entry_allowed, note
    } | null
  }],
  regime: { regime, single_cap, entry_blocked } | null,   // judgement 실패 시 null
  sort_by,                            // 에코(enum밖은 "registered"로 폴백)
  partial_failure: [ ticker… | "regime" ]
}
POST /api/watchlist {ticker, stock_name?, reason?, target_price?, user_id?} → {ok, item}
DELETE /api/watchlist/{ticker}?user_id= → {ok}
PATCH  /api/watchlist/{ticker} {target_price, user_id?} → {ok, item}
```

상태코드: POST 불량 ticker=400, POST 상한 초과(신규)=409, PATCH 미등록=404, target 음수=422, 그 외 200.

## main.py에 추가 필요 (리더 전담 — 나는 미편집)

1. import (다른 라우터 import 근처, `api/main.py:77-78` 스타일):
   ```python
   from api.watchlist import router as watchlist_router  # noqa: E402
   ```
2. include (`api/main.py:80-81` 근처):
   ```python
   app.include_router(watchlist_router)
   ```
3. CORS (`api/main.py:36`):
   ```python
   allow_methods=["GET", "POST", "DELETE", "PATCH"],   # DELETE·PATCH 추가
   ```

## POST 상한 게이트 (후속 보강 — 계획 §리스크 "초과 시 WATCHLIST_MAX_ITEMS에서 방어")
- POST /api/watchlist: **신규 종목이 현재 개수 ≥ WATCHLIST_MAX_ITEMS(30)면 409(watchlist full) 거부 + 저장 안 함**. 기존 ticker 갱신(upsert)은 개수를 안 늘리므로 허용(existing is None 검사).
- test_watchlist_route.py 추가 2케이스(monkeypatch로 상한 2로 낮춰 결정적): 상한에서 신규 거부(409·저장 0·기존 유지), 상한에서 upsert 허용(200·개수 그대로). 라우트 17 passed, 전체 403 passed.

## 미해결 이슈 / 주의
- `_resolve_stock_name`의 inquire_price 폴백은 normalize_price에 name 필드가 없어 실질 미동작(마스터+ticker 폴백만 유효). 계획 §51 문구를 따라 방어적으로 두 경로 유지 — 이름 해석 실패해도 추가는 성공(이름=ticker 폴백).
- store는 in-process threading.Lock만 — 다중 프로세스/Lambda는 각자 read-modify-write 경합 가능(클라우드 전환 시 DynamoDB conditional write로 대체, 계획 §5 계약 유지).
