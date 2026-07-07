# W08 data-engineer — KIS 종목 어댑터 3종 + normalize 3종 + 번들 API

작업 #11. TDD(Red→Green→Refactor). 테스트는 규약대로 `tests/unit/collectors/`·`tests/unit/api/`
(콜로케이트 아님). KIS 코드는 **kis-code-assistant MCP로 검증** 후 어댑터화(추측 0).

## MCP로 확정한 KIS 사실 (추측 아님)

| function | TR_ID(real=demo) | PATH | output | 핵심 필드 |
|---|---|---|---|---|
| inquire_price | `FHKST01010100` | `/uapi/domestic-stock/v1/quotations/inquire-price` | 단일 dict | `stck_shrn_iscd`,`stck_prpr`,`prdy_ctrt`,`per`,`pbr`,`eps`,`bps`,`w52_hgpr`,`w52_lwpr`,`hts_avls` |
| finance_income_statement | `FHKST66430200` | `/uapi/domestic-stock/v1/finance/income-statement` | 리스트 | `stac_yymm`,`sale_account`,`bsop_prti`,`thtr_ntin` |
| finance_financial_ratio | `FHKST66430300` | `/uapi/domestic-stock/v1/finance/financial-ratio` | 리스트 | `stac_yymm`,`eps`,`bps`,`roe_val` |

**함정(MCP 확정)**:
- 재무 2종 params 키 **대소문자 혼합**: `FID_DIV_CLS_CODE`(대문자, "0"=년) + `fid_cond_mrkt_div_code`·`fid_input_iscd`(소문자). 통일 금지 — 통일하면 파라미터 오류.
- 재무 output은 행 1개일 때 **단일 dict**로 오는 변형 존재(MCP 예제가 `if not isinstance(list): [output]`로 방어) → `normalize._output_rows`가 리스트로 정규화.
- inquire_price output에 **조회시점 날짜 필드 없음**(실시간 시세) → `as_of=None`(키는 계약상 유지).
- ROE는 `roe_val`(≠ `roe`). 시가총액은 `hts_avls`(억원 단위 문자열).

## 테스트 목록 → 구현 (test-first 증거)

### Phase 1 — normalize 3종 (`tests/unit/collectors/test_normalize.py`)
Red(스켈레톤 `{}`/`[]` → assertion 실패 5건) → Green(`collectors/kis/normalize.py`):
- `test_normalize_price_shape` — 11키 clean snake(raw stck_prpr 노출 금지), 값 코어스
- `test_normalize_price_missing_fields_are_graceful` — 필드 부재/빈 output → None(KeyError 금지)
- `test_normalize_income_statement_shape` — 3연도 [{period,revenue,operating_income,net_income}], 순서 보존
- `test_normalize_income_statement_empty_output_is_empty_list` — 빈/부재 → []
- `test_normalize_income_statement_single_dict_output_coerced_to_list` — 단일 dict 변형 방어
- `test_normalize_financial_ratio_shape` / `_empty_output_is_empty_list` — roe←roe_val

### Phase 2 — 어댑터 3종 (`tests/unit/collectors/test_kis_adapters.py`)
Red(ImportError) → Green(신규 3파일):
- `test_inquire_price_returns_normalized` — TR_ID/PATH/params(J·ISCD) 확정
- `test_finance_income_statement_returns_normalized` — TR_ID + **대소문자 혼합 params 키** 검증
- `test_finance_financial_ratio_returns_normalized` — 동일 + roe 값
- `test_current_price_adapters_have_no_cache_param__plan_7_1` — inquire_price 시그니처에 `cache` 인자 부재(원칙1)

### Phase 3 — cache/keys (`tests/unit/cache/test_keys.py`)
- `test_stock_meta_sub_key` — `stock:meta:{ticker}:{section}`, 상위 프리픽스 스킴 단일화

### Phase 4 — 번들 (`tests/unit/api/test_detail.py`, 17 테스트)
Red(ImportError) → Green(`api/detail.py` + main 라우터 등록). RoutingStubClient가 tr_id(차트는 period)로 fixture 라우팅 → 오케스트레이션·엔진 조립을 실코드로 통과:
- 정상: 계약 shape / year_end_prices 월봉 조립(period=stac_yymm→close, 단일호출) / 엔진 배선(current_per=12.34, pos_52w≈54.07) / regime_gate(수축 per_max=20, per_over False) / **과열 per_max=None → entry_blocked True**
- 부분실패(parametrize 4섹션): 섹션 예외 → null + partial_failure + 나머지 생존 + 항상 계약 shape
- degraded: 빈 income/ratio output → 'financials' partial_failure 승격(섹션 자체는 not None)
- regime None: judgement None → regime_gate None + 'regime' partial_failure
- 캐시 3원칙: financials·basic만 저장 / **valuation 무캐시(원칙1)** / degraded 무저장(원칙2) / financials 실패 시 basic까지 무저장(게이트 묶음)
- 라우트: 계약 200 / 매크로 실패 → regime degraded 하지만 종목 정상

### Phase 5 — 라이브 게이트 (`tests/live/test_live_stock_bundle.py`, `@pytest.mark.live`)
키 없으면 skip(기본 스위트 green 무영향). 계획 "남은 라이브 확인" 4항목:
1. 재무 히스토리 연수 ≥ MIN_HISTORY_YEARS(3)
2. avg_per EPS/주가 조정기준 일치(PER_year vs 현재 PER 스케일 — 액면분할 불일치 표면화)
3. 재무 API demo 도메인 지원 여부(미지원=KisApiError→문서화 skip)
4. 일봉 6개월 창 회당 행 상한

## 최종 번들 응답 shape — `GET /api/detail/{ticker}/bundle` (항상 200)

```jsonc
{
  "ticker": "005930",
  "basic":     { "ticker","name","sector","listed_shares","capital","par_value","security_group" } | null,
  "valuation": { "ticker","price","change_rate","per","pbr","eps","bps",
                 "week52_high","week52_low","market_cap","as_of":null } | null,   // 라이브·무캐시
  "financials": {                                                                  // null | 아래
    "income": [ { "period":"202312","revenue":float,"operating_income":float,"net_income":float }, ... ],
    "ratio":  [ { "period":"202312","eps":float,"bps":float,"roe":float }, ... ],
    "year_end_prices": { "202312": 78500.0, ... }   // 2차 월봉 조립(avg_per 재료)
  },
  "chart":     { "ticker","candles":[ { "date":"YYYYMMDD","open","high","low","close","volume" }, ... ] } | null,
  "summary":   { rev_cagr, op_cagr, current_per, avg_per, per_vs_avg, valuation_label,
                 rsi, ma20_gap_pct, pos_52w_pct, sample_years, notes:[] },         // stock.summary(항상 dict)
  "regime_gate": { regime, per_max, pbr_max, single_cap, per_over, pbr_over, entry_blocked, note } | null,
  "indicator_config": { "ma_period":20, "rsi_period":14 },   // stock.constants.INDICATOR_CONFIG(SSOT)
  "partial_failure": []   // ⊂ { basic, valuation, financials, chart, regime }; 'financials'는 degraded 시에도
}
```

fixtures 신규: `kis_inquire_price.json`, `kis_income_statement.json`, `kis_financial_ratio.json`, `kis_monthly_chart.json`(년말가 매칭용, 캔들 date[:6]=period).

## 결과
- `uv run pytest -q` → **184 passed, 9 deselected(live)**. 회귀 없음.
- 안전 게이트: 주문 API 0(신규 파일에 order/buy/sell·주문 TR_ID·엔드포인트 0) · detail/summary/constants에 openai/anthropic import 0 · 라이브 섹션(valuation/chart) 캐시 프리픽스 0(무캐시 시그니처 + 명시 게이트).

## 미해결 (라이브 미검증 — real 키 `-m live` 필요)
- **avg_per EPS/주가 조정기준(액면분할)**: `AVG_PER_VERIFIED=False` 유지 중. 게이트 통과 전 엔진이 avg_per/valuation_label None 폴백. 삼성전자(2018 50:1 분할)로 검증 후 리더/quant가 True 전환 결정.
- **재무 API demo 미지원 가능성**: demo 환경이면 financials degraded가 의도된 동작.
- **일봉 회당 행 상한**: 6개월 단일호출 부족 시 창 축소/페이지네이션(P2).
- 년말가 월봉 date가 "YYYYMMDD"(월말 거래일) 가정 — date[:6]로 period 매칭. 라이브 #2에서 함께 확인됨.

## 리더 확인 필요 지점
- `_REGIME_INPUT_MAP`(collector→engine 키)이 `api/main.py`와 `api/detail.py`에 **중복**. 공유 헬퍼 추출은 순환 import 회피 위해 별도 모듈 필요 → 리더 판단(현재는 4줄 중복 + 주석 명시).
- 일봉 adj_price=`0`(수정주가, 기술적 연속성) / 월봉 adj_price=`1`(원주가, 재무 EPS 정합) — 조정기준 라이브 검증 결과에 따라 조정 가능.
