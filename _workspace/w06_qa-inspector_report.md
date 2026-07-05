# QA 리포트 — T0 스캐폴딩 + T1 캐시 레이어 (2026-07-05)

## 요약: 통과 9 / 실패 0 / 미검증 5

incremental QA. data-engineer T1(캐시 레이어) 착지분 + T0 스캐폴딩 검증.
KIS 어댑터·지표 수집기는 미착지 → "미검증"으로 분류(실패 아님).

---

## 통과 항목

### 1. 전체 스위트 green (스펙 §3.5 TDD-1)
- `uv run pytest -q` → **19 passed in 0.02s**. 파일 존재가 아닌 실제 green 확인.

### 2. 원칙1 — 현재가 캐시 금지 (화이트리스트) [양쪽 동시 읽기]
- 생산자: `cache/policy.py:17-21` `ALLOWED_PREFIXES = ("macro:", "stock:meta:", "kis:token:")` — 현재가 프리픽스 `stock:price:`가 화이트리스트에 **부재**.
- `cache/policy.py:28-39` `is_cacheable`: 허용 프리픽스면 True, 그 외 **CachePolicyError raise**(조용한 통과 아님).
- 소비자(테스트): `tests/unit/cache/test_policy.py:15-18` `is_cacheable("stock:price:005930")` → `pytest.raises(CachePolicyError)` 로 거부 고정. `:33-36` unknown 프리픽스(`random:foo`)도 거부 검증(화이트리스트 방식 확인).
- 키 컨벤션(`cache/keys.py`)에 현재가 네임스페이스 헬퍼 자체가 없음(`:8-17` macro/stock_meta/kis_token만) — 네임스페이스 부재로 이중 방어.

### 3. 원칙2 — 실패 응답 캐시 미저장 (partial_failure 가드) [양쪽 동시 읽기]
- 생산자: `cache/policy.py:42-56` `cache_if_clean`. `:49` 원칙1 가드 선행 → `:51-53` `partial_failure` truthy면 `cache.set` 생략하고 False 반환 → `:55` clean일 때만 set.
- 소비자(테스트): `tests/unit/cache/test_policy.py:41-46` partial_failure=["fred"]일 때 `cached is False` **및 `spy_cache.set_calls == []`** — SpyCache로 set 미호출을 실제 검증(가짜 통과 아님).
- `:49-58` clean(빈 리스트)일 때 set 1회 호출 + 저장된 key/value/ttl까지 검증. `:61-66` partial_failure 키 부재 시 clean 간주. `:69-74` cache_if_clean도 금지 프리픽스 거부(이중 방어) + set 미호출 검증.

### 4. LocalCache/FileCache TTL 결정성 (스펙 §4)
- `cache/local.py` clock 주입으로 TTL 결정적 테스트. `tests/unit/cache/test_local.py:25-33`(만료 경계), `:36-42`(FileCache 인스턴스 간 영속 = 토큰 재사용) 실동작 검증.

### 5. 가짜 테스트 스크리닝 (스펙 §3.5-6) — 통과
- `grep "assert True|assert 1|pass$" tests/` → 0건.
- 모든 캐시 테스트가 결과값을 assert에 사용(반환값 + set_calls 상태 양방향). 결과 미사용 테스트 없음.

### 6. 모킹 남용 없음 (스펙 §3.5-5) — 통과
- LocalCache/FileCache 테스트는 **실제 구현**을 실행(mock 없음).
- policy 테스트의 SpyCache(`conftest.py:28-47`)는 경계(캐시 저장소) mock으로 정당 — 내부 로직(is_cacheable/cache_if_clean)은 실제 실행됨. 경계 밖 로직 mock 없음.

### 7. API 키 하드코딩 부재 (스펙 §1 안전)
- `grep -rnE "(app_?key|secret|api_?key)\s*=\s*['\"][A-Za-z0-9]{10,}" --include="*.py"` → **0건**.
- `infra/config.py:19-25` `_require`가 미설정 시 하드코딩 fallback 없이 ConfigError. `tests/unit/test_scaffold.py:12-21`이 이를 고정.

### 8. 캐시 저장 경로에 시세 필드 부재 (스펙 §1 안전)
- `grep -rniE "price|등락|prpr|현재가|change_rate|stck_prpr" cache/` 히트 5건 전부 **주석/독스트링**(policy.py:3,4,16,38 / keys.py:3) — 실제 저장 필드 아님. 캐시 값 shape에 시세 필드를 넣는 코드 경로 없음.

### 9. 스펙 대조 — 테스트 변형 흔적 없음 (스펙 §3.5-4)
- plan §7(`invest_develop_PLAN.md:437-439`)의 원칙1(메타만 수 시간 캐시, 현재가 금지)·원칙2(partial_failure 검사 후 저장 생략)와 구현·테스트 기대값 정확히 일치. 스펙에 맞춰 조립한 흔적, 임계값 역맞춤 흔적 없음.

---

## 미검증 (대상 코드 미착지 — 실패 아님)

1. **주문 API 호출 금지 grep** — KIS 어댑터/클라이언트 미착지(T2~T3 진행 중). 현재 코드베이스 `grep 주문|order_cash|...` 0건이나, 어댑터 착지 후 재검증 필요(regression check 대상).
2. **캐시 통합 배선** — 수집기가 cache_if_clean을 실제 호출하는 배선(T8)은 미착지. 정책 함수 단위 검증만 완료, 실제 호출부 미존재.
3. **현재가 실시간 조회 경로** — 시세를 캐시 우회해 직접 조회하는 소비자 코드(팝업/번들 API) 미착지. 원칙1의 소비자측 준수는 향후 검증.
4. **3중 일관성(임계값 코드↔프롬프트↔스키마)** — LLM/quant 계층 미착지. 이번 범위 밖(지시대로 건너뜀).
5. **단정 표현·면책 고지** — 프롬프트 파일 미착지. LLM 계층 착지 후 검증.

---

## 안전 실패: 없음
안전 항목(API 키 하드코딩·시세 캐시 저장·주문 API) 현 시점 위반 0건.

---

# QA 리포트 (append) — T2 KIS 인증/클라이언트 + T3 조회 어댑터 5종 (2026-07-05)

## 요약: 통과 7 / 실패 1 / 미검증 3
안전 실패 없음. 실패 1건은 "플래그된 취약점(multiprice 방어조회)"의 테스트 커버리지 누락 — 크래시 아님(코드는 graceful 실증), 회귀 테스트 부재.

---

## 통과 항목

### 1. 전체 스위트 안정 green (스펙 §3.5 TDD-1)
- `uv run pytest -q` → **54 passed** (3연속 재실행 동일). T2+T3 45개 + T4/T5-7 landing분 포함.
- 순서 오염 없음: client 테스트를 fred/vix/fear_greed 뒤에 배치해도 12 passed(responses 격리 정상).
- 관측: data-engineer가 T5-T7를 쓰던 과도기 순간 한 번 `4 failed/50 passed`(client 2 + fred + vix)가 잡혔으나, 반쓰인 파일 상태였고 직후 54 passed로 안정화 — 재현 불가, 실패로 분류하지 않음.

### 2. 주문 API 부재 재검증 (이전 미검증 → 통과) (스펙 §1 안전)
- `grep -rniE "order_cash|order_rvsecncl|buy_order|sell_order|buy|sell|주문|매수|매도" collectors/` 실질 히트 0건.
- 유일 히트 `client.py:5`는 "매매 주문 계열은 구현하지 않는다(조회 전용)" 주석. 주문 TR_ID(TTTC08xx 등) 0건.
- balance TR_ID는 조회용 `TTTC8434R/VTTC8434R`(잔고조회, 주문 아님) — `balance.py:10`.

### 3. API 키 하드코딩 부재 (스펙 §1 안전)
- `grep collectors/` 0건. `client.py:42-46` `appkey=self._config.app_key`/`appsecret=self._config.app_secret`, `auth.py:36-37` `config.app_key`/`config.app_secret` — 전부 infra.config(환경변수 로드) 경유. 리터럴 키 없음.

### 4. 원칙1 시그니처 강제 (스펙 §1 현재가 캐시 금지) [코드+테스트]
- 현재가 계열 어댑터에 cache 인자 부재 확인: `quote.py:13`, `multiprice.py:15`, `balance.py:13` 모두 `cache` 파라미터 없음.
- `test_kis_adapters.py:85-93` `test_current_price_adapters_have_no_cache_param`(parametrize: quote/multiprice/balance)가 `inspect.signature`로 "cache not in params"를 고정. 시세 필드가 캐시로 새는 경로 원천 차단.
- chart(`chart.py:13`)·stock_info(`stock_info.py:15`)도 현재 cache 인자 없음 — 이들의 조건부/메타 캐시 배선은 T8에서 policy.cache_if_clean 경유 예정(각 모듈 docstring 명시). stock:meta: 키 경로는 keys.py/policy.py에 이미 존재.

### 5. 반환 shape 계약 교차검증 (스펙 §3 경계면) [양쪽 동시 읽기]
- 5종 정규화 반환 dict ↔ 테스트 기대 shape/값 일치, 전부 fixture(load_fixture) 기반:
  - balance: `normalize.py:54-79` ↔ `test_normalize.py:33-50`(holdings 2건, 음수 pnl -2.78 보존, summary net_asset).
  - quote: `normalize.py:82-96`(output1/output2 병합) ↔ `test_normalize.py:55-64`.
  - daily_chart: `normalize.py:99-114` ↔ `test_normalize.py:69-81`(candles OHLCV).
  - multiprice: `normalize.py:117-132` ↔ `test_normalize.py:86-94`.
  - stock_info(메타): `normalize.py:153-164` ↔ `test_normalize.py:99-106`(sector/listed_shares).
- 어댑터 레벨도 `test_kis_adapters.py`가 TR_ID·params 조립을 StubClient(경계 mock)로 검증. env별 TR_ID 분기(real TTTC8434R / demo VTTC8434R) 실검증.

### 6. auth 토큰 재사용/재발급 정책 (스펙 §2, §5)
- `test_auth.py` 4개 실로직 통과(HTTP 경계만 responses mock): 발급+expires_at 계산, 부재 시 발급+저장, 만료 여유 시 재사용(HTTP 0회), 만료 임박(<1h) 재발급. FileCache 영속으로 KIS 재발급 차단 규약 반영(`auth.py:50-60`).

### 7. client HTTP 경계 (스펙 §2) [양쪽 동시 읽기]
- `test_client.py` 5개: 인증 헤더 주입(authorization/appkey/appsecret/tr_id/custtype), env 도메인 분기(real openapi:9443 / demo openapivts:29443), extra_headers 병합, `raise_for_status` 에러 전파. `client.py:40-58`과 일치.

---

## 실패 항목

### [테스트커버리지 / 플래그된 취약점] multiprice 방어조회 fallback 경로 미검증
- **위치**: `collectors/kis/normalize.py:117-132`(normalize_multiprice) / 테스트 `tests/unit/collectors/test_normalize.py:86-94`
- **현상**: 방어조회 코드
  `ticker = pick(row,"inter_shrn_iscd") or pick(row,"mksc_shrn_iscd")`,
  `price = to_float(pick(row,"inter2_prpr") or pick(row,"stck_prpr"))`
  의 **2차 후보키(mksc_shrn_iscd / stck_prpr)** 와 **전 후보키 부재 → None graceful** 경로에 테스트가 없음. 해피패스 `test_normalize_multiprice_shape`는 1차 후보키만 담은 fixture(`kis_intstock_multprice.json`)만 사용.
- **graceful 여부(런타임 실증)**: 크래시 없음 — 누락키 행 → `{ticker:None, price:None, change_rate:None}`, `output` 부재/None → `{items:[]}`, fallback키 행 → 정상 파싱. 즉 **코드는 안전하나 회귀 테스트로 고정되지 않음**.
- **가중 리스크**: multiprice fixture 필드명(inter_shrn_iscd/inter2_prpr) 자체가 data-engineer가 "COLUMN_MAPPING 미확보"로 플래그한 **추정값** — 해피패스 테스트도 미확정 fixture에 의존. 즉 이 어댑터는 1차키·2차키·graceful 세 경로 모두 라이브 미확정.
- **수정 방향**:
  1. `test_normalize.py`에 (a) 2차 후보키(mksc_shrn_iscd/stck_prpr)만 담은 행, (b) 후보키 전부 부재한 행(→ None graceful) 케이스 추가해 방어조회를 회귀 고정.
  2. T9 live 스모크에서 실제 output 필드명 확정 후 fixture·1차 후보키를 확정값으로 갱신(그때 추정 후보키 정리).
  - 담당: **data-engineer**

---

## 미검증 (대상 코드 미착지/범위 밖)
1. multiprice 실제 KIS output 필드명 확정 — **T9 live 스모크 대상**(현재 추정 후보키로 방어).
2. T4 섹터지수(sector_index) · T5-T7(fred/vix/fear_greed) — 이번 지시 범위 밖(다음 QA 사이클). 단 스위트가 이들 포함해 54 green임은 확인. sector_index 착지 전 순간 test_sector_index가 미존재 모듈 import로 수집을 막았으나(과도기), 모듈 착지 후 해소.
3. 캐시 통합 배선(T8) · 3중 일관성(LLM/quant) · 단정표현·면책(프롬프트) — 이전 리포트와 동일, 여전히 미착지.

---

# QA 리포트 (최종) — W06 데이터 계층 전체(T4/T5-7/T8-T10) + 회귀 (2026-07-05)

## 요약: 통과 6 / 실패 1 / 미검증 2 · 배포판정: **조건부 배포 가능**
안전 3원칙 코드+테스트 강제 + 스위트 안정 green. 유일한 열린 항목은 multiprice 어댑터(회귀 테스트 부재 + 실필드명 미확정) 1건 — graceful이라 배포 비차단.

---

## 통과 항목

### 1. 전체 회귀 + 3연속 안정성 (스펙 §3.5)
- `uv run pytest -q` → **58 passed, 4 deselected(live)** × 3연속 동일. 순서 오염 없음.
- `uv run pytest -m live` → 1 passed(fear_greed, 공개 CNN) + 3 skipped(balance/fred/vix, 키 없음). 키 부재 skip 처리 정상(`test_live_smoke.py:34,51,64`).

### 2. T8 캐시 배선 교차검증 (핵심, 스펙 §1·§4) [양쪽 동시 읽기]
- `cache/service.py:18-31` get_or_fetch: 캐시 미스 시 fetch 후 **반드시 `cache_if_clean` 경유**(`:30`)해 저장 → 원칙1(금지 프리픽스 거부)·원칙2(partial_failure 시 저장 생략) 강제.
- 메타/매크로만 배선, **현재가 경로 미배선(원칙1 최종)** — 3중 확인:
  1. 어댑터 시그니처에 cache 인자 부재(이전 사이클 확인).
  2. get_or_fetch docstring 및 현재가 경로 미사용.
  3. `test_integration.py:53-59` `test_current_price_path_never_calls_cache_set` — quote 어댑터 호출 후 `spy_cache.set_calls == []` 실검증.
- 원칙2도 배선 레벨 검증: `test_integration.py:45-50` partial_failure 응답은 2회 호출해도 `set_calls == []`(매번 재시도).

### 3. fear_greed requests_cache 전역오염 격리 (스펙 §3.5-5)
- `collectors/fear_greed.py:16-24` `_cnn_get`가 `import fear_and_greed`를 **함수 내부 지연 import** + 주석으로 사유 명시(requests_cache 전역 설치가 responses mock 오염). 실증: 스위트 58 passed × 3 순서오염 0 — 격리 실동작 확인.

### 4. T4 sector_index (스펙 §2) [3자 동시 읽기]
- `normalize.py:135-150`(normalize_sector_index) ↔ fixture `kis_index_price.json` ↔ `test_sector_index.py:22-42` 일치: price=2750.35, change=12.40, change_rate=0.45, advancing=520/declining=330/unchanged=80. 어댑터 TR_ID(FHPUP02100000)·MRKT_DIV(U)·params 검증.
- 지수 현재가 캐시 미배선: `sector_index.py:15` `inquire_index_price(client, index_code)` — cache 인자 부재, "실시간이라 캐시 금지" 표기.

### 5. T5-7 지표 (스펙 §3)
- IndicatorPoint 계약 일치: `collectors/base.py:13-26` indicator_point {key,value,as_of,source,prev_value}를 fred/vix/fear_greed 공용 사용. 각 테스트가 필드 검증.
- VIX 폴백 **두 경로** 테스트: `test_vix.py:18-40` yahoo 1차(source=yahoo) + yahoo 500 → FRED VIXCLS 폴백(source=fred, value=19.55).
- fear_greed graceful: `test_fear_greed.py:32-41` 실패 시 예외 미전파 + None 반환.
- FRED 4종 래퍼 series_id 검증(`test_fred.py:41-53` hy_spread/dollar_index/gdp + `:32-38` t10y2y) + 최신 non-NaN 선택(`:17-29`, '.' 결측 건너뜀).

### 6. 안전 grep 3종 클린 (스펙 §1)
- 주문 API 0건(cache/collectors/macro, "구현 안 함" 주석 제외). API키 하드코딩 0건. 현재가 캐시 저장 0건(cache/ 히트는 주석뿐).

---

## 실패 항목

### [테스트커버리지 / 이월 미반영] multiprice 방어조회 회귀 테스트 미추가 + live 미포함
- **위치**: `collectors/kis/normalize.py:117-132` / `tests/unit/collectors/test_normalize.py:84-94`(해피패스만) / `tests/live/test_live_smoke.py`(multiprice 테스트 부재)
- **현상**: 이전 사이클에 요청한 (a) 2차 후보키(mksc_shrn_iscd/stck_prpr) 행, (b) 전 후보키 부재→None graceful 회귀 테스트가 **추가되지 않음**(58 증분 +4는 test_integration.py 캐시 배선 4종). test_normalize.py의 multiprice는 여전히 1차키 fixture 해피패스 1개뿐.
- **가중**: live smoke에 multiprice 조회 테스트 자체가 없어 **T9 후에도 실 output 필드명 미확정** — 1차키/2차키/graceful 세 경로 전부 미검증 상태 유지.
- **비차단 근거**: 코드는 graceful(이전 사이클 런타임 실증 — 크래시 없음). 관심종목 일괄시세 1개 어댑터에 국한.
- **수정 방향**: ①test_normalize에 2차키 행 + 전키부재 행 케이스 추가 ②multiprice live 스모크 추가 또는 프론트 워치리스트 연동 전 필드명 확정. 담당: **data-engineer**

---

## 관찰 (실패 아님, 정보)

### cache.set 직접 호출 경로 2곳
- `cache/policy.py:55` — cache_if_clean 내부의 가드된 set(정상, THE 경로).
- `collectors/kis/auth.py:59` — 토큰(kis:token:) 저장, **cache_if_clean 우회**. 단 허용 프리픽스 + request_token 성공 후에만 저장(실패 시 raise_for_status가 예외)이라 원칙1/2 위반 아님. "get_or_fetch가 유일 set 경로" 전제는 엄밀히는 토큰 경로가 별도 존재. 방어심층상 auth도 is_cacheable를 통과시키면 더 견고하나 현재도 안전. **데이터-fetch 캐싱(메타/매크로)은 전부 cache_if_clean 경유 확인됨.**

---

## 미검증
1. multiprice 실 KIS output 필드명 — live 테스트 부재로 미확정(위 실패 항목과 연동).
2. LLM/quant 계층(3중 일관성·단정표현·면책·프롬프트) — W07+ 범위, 미착지.

---

## 배포 가능 여부 판정: 조건부 배포 가능 (GO with caveat)
- **GO 근거**: 안전 3원칙(현재가 캐시 금지·실패 응답 미저장·주문 API 부재)이 코드+테스트로 강제되고, T8 배선이 cache_if_clean 단일 게이트로 원칙1/2를 관철. 인증/조회 5종/섹터/FRED/VIX/공포탐욕/캐시 배선 전부 테스트 green 안정(58×3).
- **Caveat**: multiprice(관심종목 일괄시세) 어댑터는 실필드명 미확정 + 방어조회 회귀 테스트 부재. graceful이라 배포는 막지 않으나, **프론트 워치리스트가 이 어댑터를 실제 소비하기 전 필드명 확정 필수**. 그 전까지 multiprice 결과는 ticker/price=None 가능성 있음(크래시는 없음).

---

# QA 리포트 (회귀 재검증) — multiprice 방어조회 보강 확인 (2026-07-05)

## 결과: 이전 실패 항목 1건 → **해소(RESOLVED)**. 스위트 60 passed / 4 deselected.

data-engineer가 요청한 두 회귀 테스트를 `tests/unit/collectors/test_normalize.py`에 추가. 직접 실행·내용 확인 완료:
- `test_normalize_multiprice_uses_fallback_candidate_keys`(:97-108): 1차키 부재 + 2차 후보키(mksc_shrn_iscd/stck_prpr)만 담은 행 → ticker=005930/price=70500.0/change_rate=0.71 검증. 방어조회 `or pick(...)` **fallback 분기를 실제로 탐**(가짜 테스트 아님).
- `test_normalize_multiprice_all_candidate_keys_absent_is_graceful`(:111-116): 후보키 전부 부재 행 → `{ticker:None, price:None, change_rate:None}` 정확 검증. graceful 경로 회귀 고정.
- `uv run pytest -q` → **60 passed, 4 deselected**(기존 58 + 신규 2). 가짜 테스트/always-true 없음.

**남은 미검증(변동 없음)**: multiprice 실 KIS output 필드명 — live 확정 대상. data-engineer가 명세 §4에 T9 live로 fixture·1차 후보키 갱신 예정 기록. 이제 세 경로(1차키/2차키/graceful) 중 2차키·graceful은 회귀 고정됐고, 1차키 실필드명만 live 확정 대기.

## 배포 판정 갱신: **배포 가능(GO)**
방어조회 회귀 커버리지 확보로 이전 caveat의 "회귀 테스트 부재" 해소. 남은 것은 multiprice 1차키 실필드명 확정(live)뿐이며, graceful 보장이 회귀로 고정돼 크래시 리스크 없음. W06 데이터 계층 배포 준비 완료.

---

# QA 리포트 (최종 확정) — multiprice 회귀+라이브 게이트 재확인 (2026-07-05)

## 최종 판정: 실패 0 / **배포 가능(GO)**

리더 정정 반영 후 두 사실 직접 재확인:

### ① multiprice 회귀 테스트 존재 + 통과
- `tests/unit/collectors/test_normalize.py:97-116`에 두 테스트 존재·통과: fallback 후보키(2차키) + 전키부재 graceful. `uv run pytest -k multiprice` → **4 passed**(shape/adapter/fallback/graceful).

### ② 라이브 필드명 확정 게이트 추가 (신규, 양호)
- `tests/live/test_live_smoke.py:48-71` `test_live_kis_multiprice_confirms_field_mapping`: 실 응답에서 `items` 비어있지 않고 `ticker is not None` + `isinstance(price, float)`를 강제. 후보키가 틀리면 None → **실패로 드러나는 필드명 확정 게이트**(actionable 메시지 포함). 키 없으면 ConfigError skip.
- `uv run pytest -q` → 60 passed / 4 deselected. `-m live` → 1 passed + 4 skipped(multiprice 포함 5종 수집, 키 없어 skip).

## 결론
- 이전 사이클의 "실패 1(multiprice 회귀 미추가)"은 **해소**됨(회귀 테스트 존재+통과). 열린 코드 결함 없음.
- multiprice 1차키 실필드명은 이제 **라이브 게이트가 검증**한다 — `-m live` 실행(실 KIS 키) 시 필드명이 틀리면 게이트가 실패해 즉시 드러남. 유닛 레벨은 2차키·graceful 회귀로 고정.
- **W06 데이터 계층: 실패 0, 배포 가능(GO).** 안전 3원칙 코드+테스트 강제, 스위트 60 passed 안정, multiprice 필드명은 라이브 게이트로 상시 감시.
