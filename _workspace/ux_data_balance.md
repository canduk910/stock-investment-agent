# UX2 — 잔고(포트폴리오) 백엔드 (data-engineer)

Task #12 완료. **조회 전용**(주문/매매 0), 현재가 포함 → **캐시 없음**(원칙1). KIS 실패 graceful(항상 200).

## 리더용 — api/main.py wiring (⚠ main.py 편집은 리더 전담)

기존 라우터(watchlist/report)와 동일 패턴으로 두 줄 추가:

```python
# 지연 import 블록(다른 router import 들 근처, # noqa: E402 붙는 곳)
from api.balance import router as balance_router  # noqa: E402

# include 블록(app.include_router(...) 들 근처)
app.include_router(balance_router)
```

배치 위치: `report_router` include(현재 api/main.py:71-73) 바로 다음이 자연스럽다.

## 신규/변경 파일

- **api/balance.py** (신규): `GET /api/balance` 라우터.
  - `_build_kis_client()`(api.detail 재사용, 순환 회피) + `infra.config.kis_account()`로 (CANO, 상품코드) 로드 → `collectors.kis.balance.inquire_balance(client, cano, prdt)`.
  - KIS 예외 시 `{holdings:None, summary:None, partial_failure:['balance']}` (항상 200, `_log.warning`으로 표면화 — except pass 아님).
  - 테스트 seam: `balance._build_kis_client`·`balance._load_account` monkeypatch.
- **infra/config.py**: `kis_account() -> (cano, prdt)` 헬퍼 추가.
  - CANO: `KIS_ACNT_NO` 우선 → 없으면 `KIS_ACCOUNT_NO` 폴백(하이픈 있으면 앞 8자리만).
  - 상품코드: `KIS_ACNT_PRDT_CD_STK` → 미설정 시 `"01"`(국내주식 종합).
  - 미설정 허용(_optional) — 빈 CANO 반환(라우트가 graceful). KisConfig dataclass 필드는 안 건드림(헬퍼 방식 채택).
- **.env.example**: `KIS_ACNT_NO`·`KIS_ACNT_PRDT_CD_STK` 키 이름 추가(값 없음).
- **tests/unit/api/test_balance_route.py** (신규, 6 tests): 계약 shape·정규화값·계정 params 전달·KIS 실패 graceful·조회전용(GET만·POST/DELETE/PATCH=405). StubClient + fixture(라이브 미호출).
- **tests/unit/infra/test_kis_account.py** (신규, 7 tests): 폴백·기본값·우선순위·미설정·주문 API 부재 grep. os.environ monkeypatch(reload 안 씀 — load_dotenv .env 오염 회피).

## 확정 계약 (frontend·llm·qa 의존 — 임의 변경 금지)

```
GET /api/balance →
{
  "holdings": [
    {"ticker","name","qty"(int),"avg_price","current_price","eval_amount","pnl_amount","pnl_pct"}
  ],                          # normalize_balance output1
  "summary": {"deposit","purchase_amount","eval_amount","pnl_amount","total_eval","net_asset"},
  "partial_failure": []
}
```
- 값 타입: qty=int, 나머지 수치 필드=float|None(정규화). pnl_amount/pnl_pct는 음수 가능.
- **KIS 실패 시**: `holdings=None`, `summary=None`, `partial_failure=["balance"]` (여전히 200).
- normalize_balance 실제 반환 shape과 **정확히 일치 확인 완료**(collectors/kis/normalize.py:54 + fixture tests/fixtures/kis_inquire_balance.json). 계획서 계약과 동일 — 변경 없음.

## 검증

- `uv run pytest tests/unit/api/test_balance_route.py tests/unit/infra/test_kis_account.py -q` → 13 passed.
- `uv run pytest -q` → 472 passed, 10 deselected(라이브), 무회귀.
- 안전 grep: api/balance.py 에 order/buy/sell 실코드 0(주석만), cache.set/_META_CACHE/cache_if_clean 0, @router는 GET 1개뿐.

## 소유권·config 복구 (해결 완료)

구 data-engineer 에이전트가 Task #12 를 잘못 claim 해 config 를 동시 편집(KisConfig dataclass 에 필드 추가) → collection 에러를 냈었다. 리더가 그 에이전트를 중지시키고 소유권을 data-engineer-2(나)로 확정. **복구 완료 상태:**
- `infra/config.py`: KisConfig dataclass 는 **원상태**(구 에이전트의 필드 추가 원복). 계좌 로직은 `kis_account()` 헬퍼 단일 출처 — dataclass 를 안 건드려 다른 config 작업과 충돌 없음.
- 구 에이전트의 `tests/unit/infra/test_config.py`(reload fixture 버그: `importlib.reload(config)` 가 모듈 상단 `load_dotenv()` 로 .env 실값을 재주입 → 폴백/미설정 테스트가 로컬 .env 때문에 실패)는 제거됨. **내 격리 안정 버전으로 대체** — 동일 파일명 `tests/unit/infra/test_config.py`, reload 대신 os.environ monkeypatch 로 결정적 격리(7 tests green).

검증: `uv run pytest tests/unit/infra/test_config.py tests/unit/api/test_balance_route.py -q` → **13 passed**. 전체 `uv run pytest -q` → **472 passed** 무회귀.
