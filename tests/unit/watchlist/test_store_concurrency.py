"""Store 동시성 회귀 — read-modify-write 가 락으로 보호되는지(IMP-20).

FastAPI 는 sync POST/PATCH/DELETE 를 싱글톤 store 에 스레드풀로 디스패치한다. 락이 없으면
서로 다른 ticker 를 동시에 put 할 때 read-modify-write 경합으로 쓰기가 유실된다. 단일 스레드
테스트는 락(AtomicJsonFile.lock)을 제거해도 초록이므로, 여기서 실제 경합으로 유실 0 을 고정한다.
"""
from __future__ import annotations

import threading

from watchlist.models import WatchlistItem
from watchlist.store import JsonFileWatchlistStore


def _item(ticker: str) -> WatchlistItem:
    return WatchlistItem(ticker=ticker, stock_name=ticker, added_at="2026-01-01T00:00:00+00:00")


def _run_concurrently(fns: list) -> None:
    """모든 스레드가 배리어에서 동시에 출발해 임계영역 경합을 최대화."""
    barrier = threading.Barrier(len(fns))

    def wrap(fn):
        def _inner():
            barrier.wait()
            fn()

        return _inner

    threads = [threading.Thread(target=wrap(fn)) for fn in fns]
    for th in threads:
        th.start()
    for th in threads:
        th.join()


def test_concurrent_puts_different_tickers_no_lost_writes(tmp_path):
    store = JsonFileWatchlistStore(tmp_path / "wl.json")
    tickers = [f"{i:06d}" for i in range(16)]
    _run_concurrently([lambda t=t: store.put(_item(t)) for t in tickers])
    stored = {i.ticker for i in store.list_items("local")}
    assert stored == set(tickers)  # 유실 0 — 락 제거 시 일부 사라져 실패


def test_concurrent_update_target_same_ticker_no_corruption(tmp_path):
    store = JsonFileWatchlistStore(tmp_path / "wl.json")
    store.put(_item("005930"))
    prices = list(range(16))
    _run_concurrently([lambda p=p: store.update_target("local", "005930", float(p)) for p in prices])
    items = store.list_items("local")
    # 파일 무손상: 항목은 여전히 1개, 최종 target_price 는 경합한 값 중 하나.
    assert len(items) == 1
    assert items[0].target_price in {float(p) for p in prices}
