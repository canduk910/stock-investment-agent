"""캐시 통합 배선 테스트 — plan §4, §5, T8.

메타/매크로 경로만 cache_if_clean(정책)을 경유한다. 현재가 경로는 캐시를
아예 건드리지 않는다(원칙1). partial_failure 섞인 응답은 저장되지 않는다(원칙2).
"""
from __future__ import annotations

from cache.keys import macro_key, stock_meta_key
from cache.service import get_or_fetch
from collectors.kis import quote


class StubClient:
    def __init__(self, body):
        self._body = body

    def get(self, tr_id, path, params, extra_headers=None):
        return self._body


def test_stock_meta_fetched_then_cached_then_reused(spy_cache):
    """첫 호출은 fetch+저장, 둘째 호출은 캐시 재사용(fetch 미호출)."""
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return {"ticker": "005930", "sector": "반도체와반도체장비"}

    key = stock_meta_key("005930")
    first = get_or_fetch(spy_cache, key, fetch, ttl_seconds=3600)
    second = get_or_fetch(spy_cache, key, fetch, ttl_seconds=3600)

    assert first == second
    assert calls["n"] == 1  # 두 번째는 캐시 히트
    assert len(spy_cache.set_calls) == 1
    assert spy_cache.set_calls[0][0] == key


def test_macro_indicator_cached_via_policy(spy_cache):
    key = macro_key("T10Y2Y")
    get_or_fetch(spy_cache, key, lambda: {"key": "T10Y2Y", "value": 0.42}, ttl_seconds=86400)
    assert spy_cache.set_calls[0][0] == "macro:T10Y2Y"


def test_partial_failure_not_cached__plan_7_2(spy_cache):
    """partial_failure가 있으면 저장하지 않고 매번 재시도(fetch 재호출)."""
    value = {"data": 1, "partial_failure": ["dart"]}
    get_or_fetch(spy_cache, macro_key("dashboard"), lambda: value, ttl_seconds=60)
    get_or_fetch(spy_cache, macro_key("dashboard"), lambda: value, ttl_seconds=60)
    assert spy_cache.set_calls == []  # 한 번도 저장 안 됨


def test_current_price_path_never_calls_cache_set__plan_7_1(spy_cache, load_fixture):
    """현재가(호가) 어댑터는 캐시 배선이 없어 cache.set을 호출하지 않는다."""
    client = StubClient(load_fixture("kis_asking_price"))
    result = quote.inquire_asking_price_exp_ccn(client, "005930")

    assert result["price"] == 70500.0
    assert spy_cache.set_calls == []  # 현재가는 캐시에 저장되지 않음
