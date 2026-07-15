"""SqlWatchlistStore — Protocol roundtrip + upsert added_at 보존 + **유저 격리**(인메모리 SQLite)."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from infra.db import Base, import_models
from watchlist.models import WatchlistItem
from watchlist.sql_store import SqlWatchlistStore


@pytest.fixture
def store():
    import_models()  # WatchlistItemRow 등록
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    return SqlWatchlistStore(db)


def _item(uid, ticker, *, name="종목", reason=None, target=None, sell_target=None,
          at="2026-07-12T00:00:00+00:00"):
    return WatchlistItem(
        user_id=uid, ticker=ticker, stock_name=name, reason=reason, target_price=target,
        sell_target_price=sell_target, added_at=at,
    )


def test_put_get_list(store):
    store.put(_item("1", "005930", name="삼성전자", target=90000))
    got = store.get("1", "005930")
    assert got and got.stock_name == "삼성전자" and got.target_price == 90000
    assert [i.ticker for i in store.list_items("1")] == ["005930"]


def test_upsert_preserves_added_at(store):
    store.put(_item("1", "005930", at="2026-07-01T00:00:00+00:00", target=1))
    store.put(_item("1", "005930", at="2026-07-12T00:00:00+00:00", target=2))  # 갱신
    got = store.get("1", "005930")
    assert got.target_price == 2  # 값 갱신
    assert got.added_at == "2026-07-01T00:00:00+00:00"  # 최초 등록 시각 보존
    assert len(store.list_items("1")) == 1  # 중복 아님


def test_list_ordered_by_added_at(store):
    store.put(_item("1", "000001", at="2026-07-03T00:00:00+00:00"))
    store.put(_item("1", "000002", at="2026-07-01T00:00:00+00:00"))
    store.put(_item("1", "000003", at="2026-07-02T00:00:00+00:00"))
    assert [i.ticker for i in store.list_items("1")] == ["000002", "000003", "000001"]


def test_delete_idempotent(store):
    store.put(_item("1", "005930"))
    store.delete("1", "005930")
    assert store.get("1", "005930") is None
    store.delete("1", "005930")  # 없어도 예외 없음


def test_update_target(store):
    store.put(_item("1", "005930", target=100))
    updated = store.update_target("1", "005930", 200)
    assert updated.target_price == 200
    assert store.update_target("1", "999999", 1) is None  # 미등록 → None


# ── 매수/매도 목표가 — 프로덕션 저장소(SqlWatchlistStore) ORM 컬럼 read/write + 부분갱신 ───────
# InMemory/JsonFile 와 별개 구현이라 여기서 직접 검증(회귀 시 매수↔매도 소실=프로덕션 데이터 유실).

def test_put_get_roundtrips_sell_target(store):
    store.put(_item("1", "005930", target=80000, sell_target=120000))
    got = store.get("1", "005930")
    assert got.target_price == 80000 and got.sell_target_price == 120000


def test_upsert_updates_sell_target(store):
    store.put(_item("1", "005930", sell_target=100000, at="2026-07-01T00:00:00+00:00"))
    store.put(_item("1", "005930", sell_target=130000, at="2026-07-12T00:00:00+00:00"))  # 갱신
    got = store.get("1", "005930")
    assert got.sell_target_price == 130000
    assert got.added_at == "2026-07-01T00:00:00+00:00"  # 최초 시각 보존


def test_update_targets_sell_only_leaves_buy(store):
    # 매도만 PATCH → 매수는 그대로(sentinel _UNSET). 프로덕션 경로 데이터 유실 방지 회귀.
    store.put(_item("1", "005930", target=80000, sell_target=None))
    updated = store.update_targets("1", "005930", sell_target_price=120000)
    assert updated.sell_target_price == 120000
    assert updated.target_price == 80000  # 미제공 → 불변
    got = store.get("1", "005930")
    assert (got.target_price, got.sell_target_price) == (80000, 120000)


def test_update_targets_buy_only_leaves_sell(store):
    store.put(_item("1", "005930", target=None, sell_target=120000))
    updated = store.update_targets("1", "005930", target_price=70000)
    assert updated.target_price == 70000
    assert updated.sell_target_price == 120000  # 미제공 → 불변


def test_update_targets_none_clears_only_that_side(store):
    # None 은 '해제'(sentinel 과 구분). 매수만 해제, 매도는 미제공 → 유지.
    store.put(_item("1", "005930", target=80000, sell_target=120000))
    updated = store.update_targets("1", "005930", target_price=None)
    assert updated.target_price is None
    assert updated.sell_target_price == 120000


def test_update_targets_both_and_missing(store):
    store.put(_item("1", "005930"))
    updated = store.update_targets("1", "005930", target_price=70000, sell_target_price=120000)
    assert (updated.target_price, updated.sell_target_price) == (70000, 120000)
    assert store.update_targets("1", "999999", sell_target_price=1) is None  # 미등록 → None


def test_user_isolation(store):
    store.put(_item("1", "005930", name="A의 삼성"))
    store.put(_item("2", "000660", name="B의 하이닉스"))
    # 유저 1 은 자기 것만, 유저 2 도 자기 것만.
    assert [i.ticker for i in store.list_items("1")] == ["005930"]
    assert [i.ticker for i in store.list_items("2")] == ["000660"]
    assert store.get("1", "000660") is None  # 남의 종목 안 보임
    assert store.get("2", "005930") is None
