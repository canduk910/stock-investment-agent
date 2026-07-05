---
name: kis-data-pipeline
description: "KIS(한국투자증권) Open API 연동, FRED/CNN 공포탐욕/DART 수집기, 캐시 레이어, 번들 API 구현 방법. KIS API 코드 작성, 시세/잔고/일봉/관심종목 조회, 지표 수집기, 캐시 정책, /bundle 엔드포인트, 데이터 파이프라인 작업(신규 구현·수정·버그 픽스·확장 모두)을 하기 전에 반드시 이 스킬을 읽을 것. kis-code-assistant MCP 사용법 포함."
---

# KIS 데이터 파이프라인 구현 가이드

## 1. KIS API 연동 — kis-code-assistant MCP 필수 워크플로우

KIS API는 TR_ID·헤더·파라미터명이 기억으로 재현 불가능한 형태다(예: `FHKST01010200`). 추측으로 작성한 코드는 거의 확실히 401/파라미터 오류가 난다. 그래서 **연동 코드를 작성하기 전에 반드시 MCP로 검증된 공식 예제 코드를 가져온다**:

1. **검색**: 카테고리별 검색 도구 호출
   - 국내주식: `mcp__kis-code-assistant__search_domestic_stock_api`
   - 인증: `mcp__kis-code-assistant__search_auth_api`
   - ETF/ETN: `mcp__kis-code-assistant__search_etfetn_api` (필요 시)
   - 파라미터: `query`(원본 질문), `subcategory`, `api_name`, `function_name`, `description`, `response`
   - 결과 없으면 재시도 순서: query만 → `function_name` → `api_name` → `subcategory`
2. **코드 획득**: 검색 결과의 `url_main`(및 `url_chk`)을 `mcp__kis-code-assistant__read_source_code`에 넘겨 실제 GitHub 코드를 받는다
3. **어댑터화**: 받은 코드를 그대로 복붙하지 말고 프로젝트 구조에 맞게 변환한다 — 인증 토큰 관리 분리, 환경변수 로딩, 에러 처리, 반환 dict 정규화

### API 매핑

플랜 §8에서 확인된 함수명 (그래도 구현 전 MCP 검색으로 최신 코드 확인):

| 용도 | function_name | 검색 힌트 |
|---|---|---|
| 계좌 잔고(보유종목) | `inquire_balance` | 국내주식 |
| 관심종목 일괄 시세 | `intstock_multprice` | 국내주식 |
| 현재가/호가 | `inquire_asking_price_exp_ccn` | subcategory="기본시세" |
| 일봉 차트 | `inquire_daily_itemchartprice` | subcategory="기본시세" |
| 종목 기본정보 | `search_stock_info` | 국내주식 |

**미확정 — MCP 검색으로 함수명부터 확인 필요**:

| 용도 | 검색 시작점 |
|---|---|
| 인증 토큰 발급 | `search_auth_api`, subcategory="인증", function_name="auth_token" 후보 |
| 업종 지수(섹터 집중도) | `search_domestic_stock_api`, subcategory="업종/기타" |

새 기능이 필요하면 위 표에 없어도 먼저 MCP로 검색한다. PER/PBR 등 시세 응답에 이미 포함된 필드가 많으므로(`response="PER"`로 검색 가능), 별도 API를 추가하기 전에 기존 응답 필드를 확인한다.

### 인증 주의사항

- 토큰은 발급 후 24시간 유효, **재발급 남발 시 KIS가 차단**한다 — 토큰을 파일/캐시에 저장하고 만료 임박 시에만 재발급
- 모의투자/실전투자는 도메인과 TR_ID가 다르다 — 환경변수로 분기
- 앱키/시크릿은 환경변수 전용 (`KIS_APP_KEY`, `KIS_APP_SECRET`). 코드·로그에 노출 금지

## 2. 외부 지표 수집기

| 지표 | 소스 | 구현 |
|---|---|---|
| 장단기 금리차 | FRED `T10Y2Y` | `fredapi` 또는 REST, `FRED_API_KEY` |
| HY 신용스프레드 | FRED `BAMLH0A0HYM2` | 〃 |
| 달러지수 | FRED `DTWEXBGS` | 〃 |
| GDP(버핏지수 분모) | FRED | 〃 + KRX 시총(KIS)과 결합 계산 |
| VIX | 야후파이낸스(`^VIX`) 또는 FRED `VIXCLS` | 실패 시 상호 폴백 |
| 공포탐욕지수 | CNN 비공식 | `fear-and-greed` 파이썬 래퍼 우선, 실패 처리 필수 |

- 소스별 어댑터 1파일. 공통 반환 형식: `{"key": str, "value": float, "as_of": date, "source": str}`
- **[P2] 방향 신호**: FRED 시계열을 어차피 받으므로 N개월 전 값도 함께 반환하면 §4.6 모멘텀 확장이 쉬워진다
- CNN 스크래핑은 페이지 구조 변경으로 언제든 깨진다 — 예외를 잡아 `partial_failure`로 기록하고 절대 전체 파이프라인을 죽이지 않는다

## 3. 캐시 정책 3원칙 (위반 시 QA에서 실패 처리됨)

1. **현재가·등락률은 캐시 금지.** 시세는 요청마다 KIS 직접 조회. 낡은 가격은 사용자 관점에서 환각과 같다. 캐시 허용 대상: 섹터·52주 고저·PER·PBR 등 메타 정보(수 시간 TTL), 매크로 지표(지표 갱신 주기에 맞춤).
2. **실패 응답은 캐시에 저장하지 않는다.** 저장 전 `partial_failure`가 비어있는지 검사 — 실패가 섞이면 저장을 생략해 다음 요청이 재시도하게 한다. 실패를 캐시하면 원인이 해결돼도 TTL까지 깨진 데이터가 계속 나간다.
3. **[P2] 프리웜**: 매일 KST 00:05 스케줄러가 매크로 지표를 미리 수집·캐시.

캐시 키 컨벤션: `macro:{indicator}` (예: `macro:T10Y2Y`), `stock:meta:{ticker}`. 로컬 개발은 dict/파일 캐시로 시작해 인터페이스만 ElastiCache 호환으로 둔다.

## 4. 번들 API 패턴 (N+1 방지)

`GET /api/detail/{ticker}/bundle` 하나로 팝업에 필요한 데이터를 전부 반환한다:

```python
def get_stock_bundle(ticker: str) -> dict:
    """KIS·DART 병렬 조회. 한 소스 실패가 전체를 죽이지 않는다."""
    results, failures = {}, []
    with ThreadPoolExecutor() as ex:
        futures = {
            "basic": ex.submit(fetch_basic, ticker),        # KIS 현재가 — 캐시 금지
            "financials": ex.submit(fetch_financials, ticker),  # DART
            "valuation": ex.submit(fetch_valuation, ticker),
            "chart": ex.submit(fetch_daily_chart, ticker),   # KIS 일봉
        }
        for key, fut in futures.items():
            try:
                results[key] = fut.result(timeout=10)
            except Exception:
                results[key] = None
                failures.append(key)
    results["partial_failure"] = failures
    return results
```

- 실패 섹션은 `null` + `partial_failure` 리스트 기록. 프론트는 이 리스트로 섹션별 "일시 조회 불가"를 표시한다
- 매크로 대시보드(지표 7종 병렬 수집)에도 동일 패턴 적용
- `partial_failure`가 비어있지 않으면 이 응답을 캐시에 저장하지 않는다 (원칙 2)

## 5. 금지 사항

- **매매 주문 API(현금주문·정정취소 등 order 계열)는 검색도 구현도 하지 않는다.** 이 프로젝트는 조회 전용이다 (플랜 원칙 1).
- 실패를 조용히 삼키는 `except: pass` 금지 — 최소한 `partial_failure` 기록 또는 로그.
