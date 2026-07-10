"""워치리스트 CRUD 라우트 — plan §"api/watchlist.py"·Phase 3.

api/detail.py 의 _build_kis_client·_build_judgement 를 재사용(순환 import 회피 —
detail 은 api.main 을 import 하지 않으므로 사이클 없음. **api.main 을 참조하지 않는다**).
라우트는 얇게: client·judgement·store 조합 → 순수 서비스(watchlist.service)로 조립.

## 계약(frontend 의존 — 임의 변경 금지)
- GET  /api/watchlist?sort_by=&user_id= → {items, regime, sort_by, partial_failure}
- POST /api/watchlist {ticker, stock_name?, reason?, target_price?, user_id?} → {ok, item}
- DELETE /api/watchlist/{ticker}?user_id= → {ok}
- PATCH  /api/watchlist/{ticker} {target_price, user_id?} → {ok, item}

조회 전용(order/buy/sell 없음). judgement 실패 → regime degraded(항상 200, service 내부에서
partial_failure 에 'regime'). ticker 불량 → 400(저장 안 함). target 음수 → 422(Pydantic ge=0).
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

# api.detail 재사용(순환 회피 — detail 은 api.main 미참조).
from api.deps import assert_valid_ticker
from api.detail import _build_judgement, _build_kis_client
from collectors.kis import inquire_price
from collectors.stock_master import load_stock_master, search_stocks
from watchlist import service
from watchlist.constants import (
    DEFAULT_USER_ID,
    SORT_KEYS,
    WATCHLIST_MAX_ITEMS,
    WATCHLIST_STORE_PATH,
)
from watchlist.models import WatchlistItem
from watchlist.store import JsonFileWatchlistStore

router = APIRouter()

# 싱글톤 durable store(로컬 스탠드인 — 배포 시 DynamoDB 구현체 교체).
_STORE = JsonFileWatchlistStore(WATCHLIST_STORE_PATH)


def _get_store():
    """store 접근 진입점(테스트는 이 함수를 monkeypatch → 인메모리 격리)."""
    return _STORE


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


# ── 요청 바디 ────────────────────────────────────────────────────────────────

class AddRequest(BaseModel):
    # ticker 정규식은 라우트에서 명시 검증(불량 ticker=400 명확 안내 / target 음수=422 로 구분).
    ticker: str
    stock_name: str | None = None
    reason: str | None = None
    target_price: float | None = Field(default=None, ge=0)
    user_id: str | None = None


class PatchRequest(BaseModel):
    target_price: float | None = Field(default=None, ge=0)
    user_id: str | None = None


# ── stock_name 해석 ──────────────────────────────────────────────────────────

def _resolve_stock_name(client, ticker: str) -> str:
    """stock_name 미제공 시 이름 해석: 마스터 exact match 우선 → inquire_price 폴백 → ticker.

    실패해도 예외를 던지지 않는다(추가는 성공시킨다 — 이름은 부가 정보).
    """
    try:
        master = load_stock_master()
        for hit in search_stocks(master, ticker, limit=5):
            if hit.get("ticker") == ticker and hit.get("name"):
                return hit["name"]
    except Exception:
        pass
    try:
        val = inquire_price.inquire_price(client, ticker)
        name = (val or {}).get("name")  # inquire_price 는 이름을 주지 않을 수 있음
        if name:
            return name
    except Exception:
        pass
    return ticker  # 최후 폴백 — 코드 자체(프론트가 표시 가능)


# ── 라우트 ───────────────────────────────────────────────────────────────────

def _normalize_sort_by(sort_by: str | None) -> str:
    """enum 밖 값은 기본(registered)로 안전 폴백. 실제 정렬은 프론트(재조회 없음)."""
    return sort_by if sort_by in SORT_KEYS else SORT_KEYS[0]


@router.get("/api/watchlist")
def get_watchlist(
    sort_by: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
) -> dict:
    """enriched 워치리스트(registered 순). judgement 실패는 service 가 regime degraded 처리."""
    uid = user_id or DEFAULT_USER_ID
    store = _get_store()
    client = _build_kis_client()
    try:
        judgement = _build_judgement()
    except Exception:
        judgement = None  # service 가 regime=None + partial_failure 'regime'
    view = service.build_watchlist_view(store, uid, client, judgement)
    view["sort_by"] = _normalize_sort_by(sort_by)
    return view


@router.post("/api/watchlist")
def add_watchlist(req: AddRequest) -> dict:
    """관심종목 추가/갱신(upsert, added_at 보존). ticker 불량은 400(명확 안내, 저장 안 함)."""
    assert_valid_ticker(req.ticker)  # IMP-02: 공유 헬퍼(api.deps, report 라우트와 대칭)
    uid = req.user_id or DEFAULT_USER_ID
    store = _get_store()
    existing = store.get(uid, req.ticker)

    # 상한 방어(계획 §리스크): 신규 종목만 상한 검사, 기존 ticker 갱신(upsert)은 개수를 안
    # 늘리므로 허용. KIS 레이트리밋 보호(리스트 enrich=종목별 병렬 시세)이자 저장 폭주 차단.
    if existing is None and len(store.list_items(uid)) >= WATCHLIST_MAX_ITEMS:
        raise HTTPException(
            status_code=409,
            detail=f"watchlist full (max {WATCHLIST_MAX_ITEMS} items)",
        )

    stock_name = req.stock_name
    if not stock_name:
        client = _build_kis_client()
        stock_name = _resolve_stock_name(client, req.ticker)

    item = WatchlistItem(
        user_id=uid,
        ticker=req.ticker,
        stock_name=stock_name,
        reason=req.reason,
        # upsert 시 added_at 은 store 가 최초값으로 보존 → 여기선 신규 시각을 준다.
        target_price=req.target_price if req.target_price is not None
        else (existing.target_price if existing else None),
        added_at=_now_iso(),
    )
    stored = store.put(item)
    return {"ok": True, "item": stored.model_dump()}


@router.delete("/api/watchlist/{ticker}")
def delete_watchlist(ticker: str, user_id: str | None = Query(default=None)) -> dict:
    """관심종목 제거(idempotent — 없어도 ok). 불량 ticker 는 400."""
    assert_valid_ticker(ticker)  # IMP-02
    uid = user_id or DEFAULT_USER_ID
    _get_store().delete(uid, ticker)
    return {"ok": True}


@router.patch("/api/watchlist/{ticker}")
def patch_watchlist(ticker: str, req: PatchRequest) -> dict:
    """목표가 갱신. 불량 ticker 는 400. 미등록 종목은 404. 음수는 Pydantic 이 422."""
    assert_valid_ticker(ticker)  # IMP-02
    uid = req.user_id or DEFAULT_USER_ID
    updated = _get_store().update_target(uid, ticker, req.target_price)
    if updated is None:
        raise HTTPException(status_code=404, detail="watchlist item not found")
    return {"ok": True, "item": updated.model_dump()}
