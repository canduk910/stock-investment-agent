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


def _item(uid, ticker, *, name="종목", reason=None, target=None, at="2026-07-12T00:00:00+00:00"):
    return WatchlistItem(
        user_id=uid, ticker=ticker, stock_name=name, reason=reason, target_price=target, added_at=at
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


def test_user_isolation(store):
    store.put(_item("1", "005930", name="A의 삼성"))
    store.put(_item("2", "000660", name="B의 하이닉스"))
    # 유저 1 은 자기 것만, 유저 2 도 자기 것만.
    assert [i.ticker for i in store.list_items("1")] == ["005930"]
    assert [i.ticker for i in store.list_items("2")] == ["000660"]
    assert store.get("1", "000660") is None  # 남의 종목 안 보임
    assert store.get("2", "005930") is None
