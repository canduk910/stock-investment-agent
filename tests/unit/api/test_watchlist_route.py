"""워치리스트 CRUD 라우트 계약 — plan §"api/watchlist.py"·Phase 3.

api.main 은 편집 대상이 아니므로(리더 전담) 로컬 앱으로 라우터만 테스트한다:
    app = FastAPI(); app.include_router(router); TestClient(app).
경계(store·_build_kis_client·_build_judgement·_resolve_stock_name)를 monkeypatch 하고,
그 안쪽 라우트 로직(검증·upsert·view 조립·부분실패)은 실제 코드를 통과시킨다.

확정 계약(frontend 의존):
- GET  /api/watchlist?sort_by=&user_id= → {items, regime, sort_by, partial_failure}
- POST /api/watchlist {ticker, stock_name?, reason?, target_price?, user_id?} → {ok, item}
- DELETE /api/watchlist/{ticker}?user_id= → {ok}
- PATCH  /api/watchlist/{ticker} {target_price, user_id?} → {ok, item}
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.watchlist as wl
from auth.deps import get_current_user
from infra.db import get_db
from macro.engine import REGIME_PARAMS
from watchlist.store import InMemoryWatchlistStore


def _judgement(regime="수축"):
    return {"regime": regime, "params": dict(REGIME_PARAMS[regime])}


def _valuation(price=80000, change_rate=1.0, per=10.0, pbr=1.0):
    return {
        "ticker": None, "price": price, "change_rate": change_rate, "per": per, "pbr": pbr,
        "eps": None, "bps": None, "week52_high": None, "week52_low": None,
        "market_cap": None, "as_of": None,
    }


@pytest.fixture
def client(monkeypatch):
    """로컬 앱 + 인메모리 store + 시세/판정 경계 stub. 종목별 시세는 기본 정상."""
    store = InMemoryWatchlistStore()
    monkeypatch.setattr(wl, "_get_store", lambda db: store)  # db 무시(인메모리 격리)
    monkeypatch.setattr(wl, "_resolve_client", lambda *a, **k: object())
    monkeypatch.setattr(wl, "_build_judgement", lambda: _judgement())
    # inquire_price 는 service 안에서 호출 → service 모듈의 것을 patch.
    monkeypatch.setattr(
        wl.service.inquire_price, "inquire_price",
        lambda client, ticker, market="J": _valuation(),
    )
    # 스파크라인 일봉도 service 안에서 호출 → 기본 2pt 종가 stub(실 KIS 회피).
    monkeypatch.setattr(
        wl.service.chart, "inquire_daily_itemchartprice",
        lambda client, ticker, start_date, end_date, period="D", adj_price="1", market="J": {
            "ticker": ticker,
            "candles": [
                {"date": "20260101", "close": 100.0},
                {"date": "20260102", "close": 110.0},
            ],
        },
    )
    # stock_name 해석(POST) — 마스터/시세 실 호출 회피.
    monkeypatch.setattr(wl, "_resolve_stock_name", lambda client, ticker: f"종목{ticker}")

    app = FastAPI()
    app.include_router(wl.router)
    # 인증·DB 의존성 오버라이드: 고정 유저(id=1) + db 는 store 가 무시하므로 None.
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    app.dependency_overrides[get_db] = lambda: None
    tc = TestClient(app)
    tc.store = store  # 테스트에서 직접 상태 조작용
    return tc


# ── GET ──────────────────────────────────────────────────────────────────────

def test_get_empty(client):
    r = client.get("/api/watchlist")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["sort_by"] == "registered"  # 기본
    assert body["partial_failure"] == []
    assert body["regime"] == {"regime": "수축"}  # 국면명만(진입게이트 폐기 — 항목3)


def test_get_returns_enriched_items(client):
    client.post("/api/watchlist", json={"ticker": "005930", "stock_name": "삼성전자"})
    r = client.get("/api/watchlist")
    body = r.json()
    assert len(body["items"]) == 1
    it = body["items"][0]
    assert it["ticker"] == "005930"
    assert it["current_price"] == 80000
    assert "entry_signal" not in it  # 종목 진입신호 폐기(항목3) — 시세·목표가만


def test_get_item_includes_spark(client):
    # Phase D: 각 item 에 spark:number[]|null(일봉 종가 시계열, 프론트 미니차트 원천).
    client.post("/api/watchlist", json={"ticker": "005930", "stock_name": "삼성전자"})
    it = client.get("/api/watchlist").json()["items"][0]
    assert it["spark"] == [100.0, 110.0]


def test_get_item_spark_null_on_chart_failure(client, monkeypatch):
    # 일봉 실패 → spark=null(graceful). 시세·나머지 필드는 정상, partial_failure 미오염.
    def _boom(*a, **k):
        raise RuntimeError("chart down")

    monkeypatch.setattr(wl.service.chart, "inquire_daily_itemchartprice", _boom)
    client.post("/api/watchlist", json={"ticker": "005930", "stock_name": "삼성전자"})
    body = client.get("/api/watchlist").json()
    it = body["items"][0]
    assert it["spark"] is None
    assert it["current_price"] == 80000
    assert body["partial_failure"] == []


def test_get_echoes_sort_by(client):
    r = client.get("/api/watchlist", params={"sort_by": "near_target"})
    assert r.json()["sort_by"] == "near_target"


def test_get_invalid_sort_by_falls_back(client):
    # enum 밖 값은 기본(registered)로 안전 폴백(500 아님).
    r = client.get("/api/watchlist", params={"sort_by": "bogus"})
    assert r.status_code == 200
    assert r.json()["sort_by"] == "registered"


def test_get_regime_degraded_when_judgement_fails(client, monkeypatch):
    def _boom():
        raise RuntimeError("FRED down")

    monkeypatch.setattr(wl, "_build_judgement", _boom)
    client.post("/api/watchlist", json={"ticker": "005930", "stock_name": "삼성전자"})
    body = client.get("/api/watchlist").json()
    assert body["regime"] is None
    assert "regime" in body["partial_failure"]
    # 시세는 정상(진입신호 폐기 — entry_signal 필드 없음).
    assert body["items"][0]["current_price"] == 80000
    assert "entry_signal" not in body["items"][0]


# ── POST ─────────────────────────────────────────────────────────────────────

def test_post_adds_item(client):
    r = client.post("/api/watchlist", json={
        "ticker": "005930", "stock_name": "삼성전자",
        "reason": "저평가", "target_price": 90000.0,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["item"]["ticker"] == "005930"
    assert body["item"]["stock_name"] == "삼성전자"
    assert body["item"]["target_price"] == 90000.0
    assert "added_at" in body["item"] and body["item"]["added_at"]
    # 실제로 store 에 들어갔는지.
    assert client.store.get("1","005930") is not None


def test_post_resolves_stock_name_when_missing(client):
    # stock_name 없으면 _resolve_stock_name 으로 해석(stub → "종목005930").
    r = client.post("/api/watchlist", json={"ticker": "005930"})
    assert r.status_code == 200
    assert r.json()["item"]["stock_name"] == "종목005930"


def test_post_invalid_ticker_rejected(client):
    r = client.post("/api/watchlist", json={"ticker": "삼성", "stock_name": "삼성전자"})
    assert r.status_code == 400
    # 저장 안 됨.
    assert client.store.list_items("1") == []


def test_post_rejected_when_at_max_items(client, monkeypatch):
    # 상한(WATCHLIST_MAX_ITEMS) 도달 시 신규 추가 거부 + 저장 안 함(계획 §리스크 방어).
    monkeypatch.setattr(wl, "WATCHLIST_MAX_ITEMS", 2)
    assert client.post("/api/watchlist", json={"ticker": "005930", "stock_name": "A"}).status_code == 200
    assert client.post("/api/watchlist", json={"ticker": "000660", "stock_name": "B"}).status_code == 200
    # 3번째 신규 종목 → 거부.
    r = client.post("/api/watchlist", json={"ticker": "035720", "stock_name": "C"})
    assert r.status_code == 409  # 한도 충돌(4xx)
    assert client.store.get("1","035720") is None  # 저장 안 됨
    assert len(client.store.list_items("1")) == 2  # 기존 2개 유지


def test_post_upsert_allowed_at_max_items(client, monkeypatch):
    # 상한 도달 상태에서도 기존 ticker 갱신(upsert)은 허용(개수 안 늘어남).
    monkeypatch.setattr(wl, "WATCHLIST_MAX_ITEMS", 2)
    client.post("/api/watchlist", json={"ticker": "005930", "stock_name": "A"})
    client.post("/api/watchlist", json={"ticker": "000660", "stock_name": "B"})
    # 이미 있는 005930 갱신 → 허용.
    r = client.post("/api/watchlist", json={"ticker": "005930", "stock_name": "A", "reason": "갱신"})
    assert r.status_code == 200
    assert r.json()["item"]["reason"] == "갱신"
    assert len(client.store.list_items("1")) == 2  # 개수 그대로


def test_post_upsert_preserves_added_at(client):
    first = client.post("/api/watchlist", json={"ticker": "005930", "stock_name": "삼성전자"})
    added_at = first.json()["item"]["added_at"]
    second = client.post("/api/watchlist", json={
        "ticker": "005930", "stock_name": "삼성전자", "reason": "갱신",
    })
    assert second.json()["item"]["added_at"] == added_at  # 최초 보존
    assert second.json()["item"]["reason"] == "갱신"
    assert len(client.store.list_items("1")) == 1  # 중복 아님


def test_post_upsert_preserves_reason_and_name_when_omitted(client):
    # 최초에 사유·이름·목표가 저장 → 재추가 시 미제공 필드는 기존값 보존(None 덮어쓰기 금지, IMP-03).
    client.post("/api/watchlist", json={
        "ticker": "005930", "stock_name": "삼성전자", "reason": "저평가", "target_price": 90000.0,
    })
    # 다른 화면의 '관심종목 추가' 버튼이 reason 미전송 + ticker 만 재전송하는 시나리오.
    r = client.post("/api/watchlist", json={"ticker": "005930"})
    assert r.status_code == 200
    item = r.json()["item"]
    assert item["reason"] == "저평가"        # 보존(기존엔 None 으로 소실됐음)
    assert item["stock_name"] == "삼성전자"   # 보존(재-resolve 로 덮지 않음 — stub '종목005930' 아님)
    assert item["target_price"] == 90000.0   # 기존 target_price 폴백(회귀 확인)


# ── DELETE ───────────────────────────────────────────────────────────────────

def test_delete_removes(client):
    client.post("/api/watchlist", json={"ticker": "005930", "stock_name": "삼성전자"})
    r = client.delete("/api/watchlist/005930")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert client.store.get("1","005930") is None


def test_delete_missing_is_ok(client):
    r = client.delete("/api/watchlist/999999")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_delete_invalid_ticker_400(client):
    # 불량 포맷 ticker 는 store 접근 전에 400(IMP-02 — report 라우트와 대칭 검증).
    r = client.delete("/api/watchlist/abc_de")
    assert r.status_code == 400


# ── GET 멤버십(경량, 시세 enrich 없음 — IMP-21) ──────────────────────────────

def test_get_membership_reflects_store(client):
    # 담기 전 false → POST 후 true. 시세 조회 없이 store 만 본다(레이트리밋 무압박).
    assert client.get("/api/watchlist/005930").json()["member"] is False
    client.post("/api/watchlist", json={"ticker": "005930", "stock_name": "삼성전자"})
    body = client.get("/api/watchlist/005930").json()
    assert body["member"] is True
    assert body["ticker"] == "005930"


def test_get_membership_invalid_ticker_400(client):
    assert client.get("/api/watchlist/abc_de").status_code == 400


def _client_as(uid):
    """같은 (monkeypatched) store 를 공유하되 다른 인증 유저로 조회하는 클라이언트."""
    app = FastAPI()
    app.include_router(wl.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uid)
    app.dependency_overrides[get_db] = lambda: None
    return TestClient(app)


def test_get_membership_scoped_to_authed_user(client):
    client.post("/api/watchlist", json={"ticker": "005930", "stock_name": "A"})  # user 1
    assert client.get("/api/watchlist/005930").json()["member"] is True  # 본인은 보임
    # 다른 유저(id=2)는 남의 종목 멤버십이 False(유저 격리 — user_id 는 토큰에서, 쿼리 조작 불가).
    assert _client_as(2).get("/api/watchlist/005930").json()["member"] is False


# ── PATCH ────────────────────────────────────────────────────────────────────

def test_patch_updates_target(client):
    client.post("/api/watchlist", json={"ticker": "005930", "stock_name": "삼성전자"})
    r = client.patch("/api/watchlist/005930", json={"target_price": 95000.0})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["item"]["target_price"] == 95000.0
    assert client.store.get("1","005930").target_price == 95000.0


def test_patch_missing_item_404(client):
    r = client.patch("/api/watchlist/999999", json={"target_price": 95000.0})
    assert r.status_code == 404


def test_patch_invalid_ticker_400(client):
    # 불량 포맷은 404(미등록)가 아니라 400(불량 코드) — store 접근 전 차단(IMP-02).
    r = client.patch("/api/watchlist/abc_de", json={"target_price": 95000.0})
    assert r.status_code == 400


def test_patch_negative_target_rejected(client):
    client.post("/api/watchlist", json={"ticker": "005930", "stock_name": "삼성전자"})
    r = client.patch("/api/watchlist/005930", json={"target_price": -1.0})
    assert r.status_code == 422  # Pydantic 검증(ge=0)


# ── 유저 격리(인증 스코프) ────────────────────────────────────────────────────

def test_watchlist_scoped_to_authed_user(client):
    client.post("/api/watchlist", json={"ticker": "005930", "stock_name": "삼성전자"})  # user 1
    # 다른 유저(id=2)는 빈 리스트(남의 관심종목 안 보임).
    assert _client_as(2).get("/api/watchlist").json()["items"] == []
    # 본인(user 1)은 자기 종목이 보인다.
    assert [i["ticker"] for i in client.get("/api/watchlist").json()["items"]] == ["005930"]


def test_watchlist_requires_auth():
    # get_current_user 오버라이드 없음 → 토큰 없으면 401(인증 필수).
    app = FastAPI()
    app.include_router(wl.router)
    assert TestClient(app).get("/api/watchlist").status_code == 401
    assert TestClient(app).post("/api/watchlist", json={"ticker": "005930"}).status_code == 401


# ── _resolve_stock_name 3분기(IMP-05: 라이브 폴백은 name 을 주는 stock_info 사용) ──

class _FakeClient:
    """KisClient.get(tr_id, path, params) 자리표시자 — body 반환 또는 예외."""

    def __init__(self, body=None, exc=None):
        self._body, self._exc = body, exc

    def get(self, tr_id, path, params, extra_headers=None):
        if self._exc:
            raise self._exc
        return self._body


def test_resolve_stock_name_master_hit(monkeypatch):
    # 마스터 exact match 가 있으면 그 이름(KIS 호출 없음).
    monkeypatch.setattr(wl, "load_stock_master", lambda: {"_": 1})
    monkeypatch.setattr(
        wl, "search_stocks", lambda master, q, limit=5: [{"ticker": "005930", "name": "삼성전자"}]
    )
    assert wl._resolve_stock_name(object(), "005930") == "삼성전자"


def test_resolve_stock_name_live_uses_stock_info(monkeypatch):
    # 마스터 미스 → KIS 기본조회(search_stock_info, prdt_name)가 이름을 준다.
    # 기존 inquire_price 폴백은 name 필드가 없어 항상 ticker 로 떨어졌다(IMP-05 죽은 코드 회귀).
    monkeypatch.setattr(wl, "load_stock_master", lambda: {})
    monkeypatch.setattr(wl, "search_stocks", lambda master, q, limit=5: [])
    body = {"output": {"prdt_name": "카카오"}}
    assert wl._resolve_stock_name(_FakeClient(body=body), "035720") == "카카오"


def test_resolve_stock_name_falls_back_to_ticker(monkeypatch):
    # 마스터 미스 + KIS 조회 실패 → 예외 삼키고 ticker 자체(추가는 성공, 이름은 부가정보).
    monkeypatch.setattr(wl, "load_stock_master", lambda: {})
    monkeypatch.setattr(wl, "search_stocks", lambda master, q, limit=5: [])
    assert wl._resolve_stock_name(_FakeClient(exc=RuntimeError("KIS down")), "035720") == "035720"
