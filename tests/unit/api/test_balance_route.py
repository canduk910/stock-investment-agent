"""잔고(포트폴리오) 라우트 계약 테스트 — plan §Phase B 백엔드 (TDD Red→Green).

GET /api/balance 는 단일 로컬 사용자 계좌의 보유종목·요약을 반환한다. inquire_balance
어댑터(client.get 경계)를 호출하고, 그 안쪽 정규화(normalize_balance)는 실제 코드로 통과시킨다.

계약(frontend 의존 — 임의 변경 금지):
  {holdings:[{ticker,name,qty,avg_price,current_price,eval_amount,pnl_amount,pnl_pct}],
   summary:{deposit,purchase_amount,eval_amount,pnl_amount,total_eval,net_asset},
   partial_failure:[]}

안전·정책 고정:
- 조회 전용(order/buy/sell 없음) — 라우트에 GET만 존재.
- 현재가(prpr) 포함 → 캐시 저장 없음(원칙1). balance 어댑터엔 cache 인자가 없다.
- KIS 실패는 graceful: 항상 200, partial_failure=['balance'], holdings/summary=None.

api.main 은 편집하지 않는다 — 로컬 FastAPI 앱에 balance router 만 include 해 테스트한다.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.balance as balance
from collectors.kis.errors import KisApiError

# 잔고 계약 최상위 키(프론트·QA 의존).
BALANCE_KEYS = {"holdings", "summary", "partial_failure"}
HOLDING_KEYS = {
    "ticker", "name", "qty", "avg_price",
    "current_price", "eval_amount", "pnl_amount", "pnl_pct", "spark",
}
SUMMARY_KEYS = {
    "deposit", "purchase_amount", "eval_amount",
    "pnl_amount", "total_eval", "net_asset",
}


class StubClient:
    """client.get 경계 — body 를 그대로 돌려주거나, fail=True 면 KisApiError 주입.

    inquire_balance 는 client.get(TR_ID[env], path, params) 한 번만 호출하므로
    tr_id 라우팅이 필요 없다(단일 응답).
    """

    def __init__(self, body=None, fail=False, env="demo"):
        self._body = body
        self._fail = fail
        self.env = env
        self.calls = []

    def get(self, tr_id, path, params, extra_headers=None):
        self.calls.append({"tr_id": tr_id, "path": path, "params": params})
        if self._fail:
            raise KisApiError("40580000", "모의투자 잔고조회 실패", tr_id)
        return self._body


@pytest.fixture
def balance_body(load_fixture):
    return load_fixture("kis_inquire_balance")


def _make_client(monkeypatch, *, body=None, fail=False):
    """balance 라우트가 참조하는 resolve_kis_client 를 stub 으로 교체.

    유저별 자격증명 해석(본인/공유/env)은 여기서 우회 — StubClient + 고정 계좌를 담은
    ResolvedKis 를 돌려준다(테스트는 실 KIS·config·토큰·DB 를 타지 않는다).
    """
    from api.detail import ResolvedKis

    stub = StubClient(body=body, fail=fail)
    monkeypatch.setattr(
        balance, "resolve_kis_client",
        lambda user, db: ResolvedKis(stub, "00000000", "01", "shared"),
    )
    # 기본은 스파크 조회 비활성(빈 dict → spark=None) — 잔고 조회 자체에 집중하는 테스트가
    # 추가 KIS 일봉 호출로 오염되지 않게. 스파크 전용 테스트는 이 stub 을 덮어쓴다.
    monkeypatch.setattr(balance, "fetch_sparks_parallel", lambda client, tickers: {})
    return stub


def _no_db():
    yield None  # resolve_kis_client 를 patch 했으므로 실제 DB Session 불요


def _app():
    from infra.db import get_db

    app = FastAPI()
    app.include_router(balance.router)
    app.dependency_overrides[get_db] = _no_db  # 옵션인증·해석 모두 DB 미사용(patch)
    return TestClient(app)


# ── 정상 경로 ────────────────────────────────────────────────────────────────

def test_balance_returns_contract_shape(monkeypatch, balance_body):
    """정상 응답: 최상위 계약 키 + holdings/summary 필드 계약 + partial_failure 비어있음."""
    _make_client(monkeypatch, body=balance_body)
    resp = _app().get("/api/balance")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data) == BALANCE_KEYS
    assert data["partial_failure"] == []

    assert len(data["holdings"]) == 2
    for row in data["holdings"]:
        assert set(row) == HOLDING_KEYS
    assert set(data["summary"]) == SUMMARY_KEYS


def test_balance_holdings_values_normalized(monkeypatch, balance_body):
    """정규화 계약: 숫자 문자열이 float/int 로, 부호(-)·콤마 처리된다(fixture 실값 검증)."""
    _make_client(monkeypatch, body=balance_body)
    data = _app().get("/api/balance").json()

    samsung = next(h for h in data["holdings"] if h["ticker"] == "005930")
    assert samsung["name"] == "삼성전자"
    assert samsung["qty"] == 10  # int
    assert samsung["avg_price"] == 68000.0
    assert samsung["current_price"] == 70500.0  # 현재가(라이브)
    assert samsung["pnl_amount"] == 25000.0
    assert samsung["pnl_pct"] == 3.67

    hynix = next(h for h in data["holdings"] if h["ticker"] == "000660")
    assert hynix["pnl_amount"] == -25000.0  # 음수 손익
    assert hynix["pnl_pct"] == -2.78


def test_balance_summary_values_normalized(monkeypatch, balance_body):
    """요약 계약: 예수금·매입액·평가액·손익·평가총액·순자산."""
    _make_client(monkeypatch, body=balance_body)
    summary = _app().get("/api/balance").json()["summary"]
    assert summary["deposit"] == 1000000.0
    assert summary["purchase_amount"] == 1580000.0
    assert summary["eval_amount"] == 1580000.0
    assert summary["pnl_amount"] == 0.0
    assert summary["total_eval"] == 2580000.0
    assert summary["net_asset"] == 2580000.0


def test_balance_passes_account_params_to_kis(monkeypatch, balance_body):
    """config 계정(CANO/ACNT_PRDT_CD)이 KIS params 로 전달된다(단일 사용자)."""
    stub = _make_client(monkeypatch, body=balance_body)
    _app().get("/api/balance")
    assert len(stub.calls) == 1
    params = stub.calls[0]["params"]
    assert params["CANO"] == "00000000"
    assert params["ACNT_PRDT_CD"] == "01"


# ── 실패 경로(graceful) ──────────────────────────────────────────────────────

def test_balance_kis_failure_is_graceful(monkeypatch):
    """KIS 예외: 항상 200, partial_failure=['balance'], holdings/summary=None(파이프라인 안 죽임)."""
    _make_client(monkeypatch, fail=True)
    resp = _app().get("/api/balance")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data) == BALANCE_KEYS
    assert data["partial_failure"] == ["balance"]
    assert data["holdings"] is None
    assert data["summary"] is None


# ── 안전(조회 전용) ───────────────────────────────────────────────────────────

def test_balance_route_is_read_only(monkeypatch, balance_body):
    """조회 전용: /api/balance 는 GET 만 — POST/DELETE/PATCH(주문 계열)는 405."""
    _make_client(monkeypatch, body=balance_body)
    client = _app()
    assert client.get("/api/balance").status_code == 200
    assert client.post("/api/balance", json={}).status_code == 405
    assert client.delete("/api/balance").status_code == 405
    assert client.patch("/api/balance", json={}).status_code == 405


# ── 미니 스파크라인(관심종목 로직 재사용) ─────────────────────────────────────

def test_balance_holdings_include_spark(monkeypatch, balance_body):
    """각 holding 에 spark(종가 시계열) 필드가 실린다 — 워치리스트 fetch_sparks_parallel 재사용."""
    _make_client(monkeypatch, body=balance_body)
    # 스파크 병렬 조회를 stub — 넘어온 티커마다 동일 시계열 반환(실 KIS 회피).
    monkeypatch.setattr(
        balance, "fetch_sparks_parallel",
        lambda client, tickers: {t: [100.0, 110.0, 105.0] for t in tickers},
    )
    data = _app().get("/api/balance").json()
    assert data["holdings"], "fixture 에 보유종목이 있어야 한다"
    for h in data["holdings"]:
        assert h["spark"] == [100.0, 110.0, 105.0]
    assert data["partial_failure"] == []


def test_balance_spark_graceful_on_failure(monkeypatch, balance_body):
    """스파크 조회 전체 실패 → 각 holding spark=None, 시세 정상·partial_failure 미오염(항상 200)."""
    _make_client(monkeypatch, body=balance_body)

    def _boom(client, tickers):
        raise RuntimeError("chart down")

    monkeypatch.setattr(balance, "fetch_sparks_parallel", _boom)
    resp = _app().get("/api/balance")
    assert resp.status_code == 200
    data = resp.json()
    for h in data["holdings"]:
        assert h["spark"] is None
        assert h["current_price"] is not None  # 시세는 정상(스파크와 독립)
    assert data["partial_failure"] == []  # 스파크 실패는 partial_failure 를 오염시키지 않음
