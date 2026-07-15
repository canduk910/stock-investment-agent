"""WatchlistStore 계약 — plan §"백엔드 신규: watchlist/store.py".

Red-first. 두 구현(JsonFileWatchlistStore, InMemoryWatchlistStore)이 같은 계약을
만족하도록 parametrize. 캐시가 아니라 durable 사용자 상태(사용자별 (user_id,ticker) 키):
put/get/list/delete/update_target, (user_id,ticker) 격리, tmp_path 재오픈 지속성,
upsert=added_at 보존, 빈 목록, 원자적 write(temp+rename).
"""
from __future__ import annotations

import json

import pytest

from watchlist.models import WatchlistItem
from watchlist.store import InMemoryWatchlistStore, JsonFileWatchlistStore


def _item(ticker="005930", user_id="local", added_at="2026-07-09T00:00:00+00:00", **kw):
    return WatchlistItem(user_id=user_id, ticker=ticker, stock_name=kw.pop("stock_name", "삼성전자"),
                         added_at=added_at, **kw)


@pytest.fixture(params=["memory", "file"])
def store(request, tmp_path):
    if request.param == "memory":
        return InMemoryWatchlistStore()
    return JsonFileWatchlistStore(str(tmp_path / "watchlist.json"))


# ── 기본 CRUD ────────────────────────────────────────────────────────────────

def test_empty_list_returns_empty(store):
    assert store.list_items("local") == []


def test_get_missing_returns_none(store):
    assert store.get("local", "005930") is None


def test_put_then_get(store):
    item = _item()
    store.put(item)
    got = store.get("local", "005930")
    assert got is not None
    assert got.ticker == "005930"
    assert got.stock_name == "삼성전자"


def test_put_then_list(store):
    store.put(_item(ticker="005930"))
    store.put(_item(ticker="000660", stock_name="SK하이닉스"))
    items = store.list_items("local")
    assert {i.ticker for i in items} == {"005930", "000660"}


def test_delete_removes(store):
    store.put(_item())
    store.delete("local", "005930")
    assert store.get("local", "005930") is None
    assert store.list_items("local") == []


def test_delete_missing_is_noop(store):
    # 없는 종목 삭제는 예외 없이 조용히 통과(idempotent).
    store.delete("local", "999999")
    assert store.list_items("local") == []


# ── upsert: 중복 추가 = 갱신, added_at 보존 ──────────────────────────────────

def test_upsert_preserves_added_at(store):
    first = _item(added_at="2026-01-01T00:00:00+00:00", reason="초기 사유")
    store.put(first)
    # 같은 (user_id,ticker) 재추가 → 갱신하되 added_at은 최초값 보존.
    second = _item(added_at="2026-12-31T00:00:00+00:00", reason="갱신 사유")
    store.put(second)
    items = store.list_items("local")
    assert len(items) == 1
    got = items[0]
    assert got.reason == "갱신 사유"  # 필드는 갱신
    assert got.added_at == "2026-01-01T00:00:00+00:00"  # added_at은 최초 보존


# ── update_target ────────────────────────────────────────────────────────────

def test_update_target(store):
    store.put(_item(target_price=None))
    updated = store.update_target("local", "005930", 95000.0)
    assert updated is not None
    assert updated.target_price == 95000.0
    assert store.get("local", "005930").target_price == 95000.0


def test_update_target_preserves_added_at(store):
    store.put(_item(added_at="2026-01-01T00:00:00+00:00"))
    store.update_target("local", "005930", 95000.0)
    assert store.get("local", "005930").added_at == "2026-01-01T00:00:00+00:00"


def test_update_target_missing_returns_none(store):
    assert store.update_target("local", "999999", 100.0) is None


# ── update_targets(매수/매도 부분 갱신, sentinel) ─────────────────────────────

def test_update_targets_sell_only_leaves_buy(store):
    store.put(_item(target_price=80000.0, sell_target_price=None))
    updated = store.update_targets("local", "005930", sell_target_price=120000.0)
    assert updated.sell_target_price == 120000.0
    assert updated.target_price == 80000.0  # 매수는 미제공 → 그대로
    got = store.get("local", "005930")
    assert got.sell_target_price == 120000.0
    assert got.target_price == 80000.0


def test_update_targets_buy_only_leaves_sell(store):
    store.put(_item(target_price=None, sell_target_price=120000.0))
    updated = store.update_targets("local", "005930", target_price=70000.0)
    assert updated.target_price == 70000.0
    assert updated.sell_target_price == 120000.0  # 매도는 미제공 → 그대로


def test_update_targets_both(store):
    store.put(_item(target_price=None, sell_target_price=None))
    updated = store.update_targets("local", "005930", target_price=70000.0, sell_target_price=120000.0)
    assert (updated.target_price, updated.sell_target_price) == (70000.0, 120000.0)


def test_update_targets_none_clears_that_field(store):
    # None 은 '해제'(sentinel 과 구분). 매수만 해제하고 매도는 미제공 → 유지.
    store.put(_item(target_price=80000.0, sell_target_price=120000.0))
    updated = store.update_targets("local", "005930", target_price=None)
    assert updated.target_price is None
    assert updated.sell_target_price == 120000.0


def test_update_targets_missing_returns_none(store):
    assert store.update_targets("local", "999999", sell_target_price=100.0) is None


# ── (user_id, ticker) 격리 ───────────────────────────────────────────────────

def test_user_isolation(store):
    store.put(_item(ticker="005930", user_id="alice"))
    store.put(_item(ticker="000660", user_id="bob", stock_name="SK하이닉스"))
    assert [i.ticker for i in store.list_items("alice")] == ["005930"]
    assert [i.ticker for i in store.list_items("bob")] == ["000660"]
    # 한 사용자 삭제가 다른 사용자에 영향 없음.
    store.delete("alice", "005930")
    assert store.list_items("alice") == []
    assert [i.ticker for i in store.list_items("bob")] == ["000660"]


def test_same_ticker_different_users_coexist(store):
    store.put(_item(ticker="005930", user_id="alice"))
    store.put(_item(ticker="005930", user_id="bob"))
    assert store.get("alice", "005930") is not None
    assert store.get("bob", "005930") is not None


# ── list_items: 등록순(added_at 오름차순) ────────────────────────────────────

def test_list_ordered_by_added_at(store):
    store.put(_item(ticker="000660", added_at="2026-03-01T00:00:00+00:00", stock_name="SK하이닉스"))
    store.put(_item(ticker="005930", added_at="2026-01-01T00:00:00+00:00"))
    store.put(_item(ticker="035720", added_at="2026-02-01T00:00:00+00:00", stock_name="카카오"))
    tickers = [i.ticker for i in store.list_items("local")]
    assert tickers == ["005930", "035720", "000660"]  # added_at 오름차순


# ── 파일 스토어 전용: 지속성·원자성 ──────────────────────────────────────────

def test_file_store_persists_across_reopen(tmp_path):
    path = str(tmp_path / "watchlist.json")
    s1 = JsonFileWatchlistStore(path)
    s1.put(_item(ticker="005930", target_price=90000.0))
    # 새 인스턴스로 재오픈 → 디스크에서 복원.
    s2 = JsonFileWatchlistStore(path)
    got = s2.get("local", "005930")
    assert got is not None
    assert got.target_price == 90000.0


def test_file_store_missing_file_is_empty(tmp_path):
    s = JsonFileWatchlistStore(str(tmp_path / "does_not_exist.json"))
    assert s.list_items("local") == []


def test_file_store_corrupt_file_is_empty(tmp_path):
    path = tmp_path / "watchlist.json"
    path.write_text("{ this is not valid json", encoding="utf-8")
    s = JsonFileWatchlistStore(str(path))
    # 손상 파일은 빈 상태로 시작(FileCache 관례) — 예외 전파 금지.
    assert s.list_items("local") == []


def test_file_store_atomic_no_temp_leftover(tmp_path):
    # 원자적 write(temp+rename)는 성공 후 temp 파일을 남기지 않는다.
    path = tmp_path / "watchlist.json"
    s = JsonFileWatchlistStore(str(path))
    s.put(_item())
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "watchlist.json"]
    assert leftovers == []


def test_file_store_valid_json_on_disk(tmp_path):
    path = tmp_path / "watchlist.json"
    s = JsonFileWatchlistStore(str(path))
    s.put(_item(ticker="005930"))
    # 디스크 내용이 파싱 가능한 JSON이어야 한다(중간 쓰기 손상 방지 회귀).
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, (dict, list))
