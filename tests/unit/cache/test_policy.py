"""캐시 정책 3원칙 고정 테스트 — plan §4, §5, kis-data-pipeline 스킬 §3.

원칙1: 현재가 캐시 금지 — is_cacheable가 금지 프리픽스를 CachePolicyError로 거부.
원칙2: 실패 응답 캐시 금지 — cache_if_clean이 partial_failure가 비면만 set.
"""
from __future__ import annotations

import pytest

from cache.policy import CachePolicyError, cache_if_clean, is_cacheable


# --- 원칙1: 현재가/금지 프리픽스 거부 -------------------------------------

def test_price_key_rejected_by_policy__plan_7_1():
    """현재가 네임스페이스(stock:price:)는 정책이 CachePolicyError로 거부한다."""
    with pytest.raises(CachePolicyError):
        is_cacheable("stock:price:005930")


def test_meta_key_allowed_by_policy__plan_7_1():
    assert is_cacheable("stock:meta:005930") is True


def test_macro_key_allowed_by_policy__plan_7_1():
    assert is_cacheable("macro:T10Y2Y") is True


def test_token_key_allowed_by_policy__plan_7_1():
    assert is_cacheable("kis:token:real") is True


def test_unknown_prefix_rejected__plan_7_1():
    """허용 목록에 없는 프리픽스도 거부 — 화이트리스트 방식."""
    with pytest.raises(CachePolicyError):
        is_cacheable("random:foo")


# --- 원칙2: 실패 응답 캐시 저장 생략 ---------------------------------------

def test_partial_failure_present_skips_cache_set__plan_7_2(spy_cache):
    """partial_failure가 비어있지 않으면 set을 생략한다."""
    value = {"data": 1, "partial_failure": ["fred"]}
    cached = cache_if_clean(spy_cache, "macro:T10Y2Y", value, ttl_seconds=60)
    assert cached is False
    assert spy_cache.set_calls == []


def test_clean_response_is_cached__plan_7_2(spy_cache):
    """partial_failure가 비어있으면 정상 저장한다."""
    value = {"data": 1, "partial_failure": []}
    cached = cache_if_clean(spy_cache, "macro:T10Y2Y", value, ttl_seconds=60)
    assert cached is True
    assert len(spy_cache.set_calls) == 1
    key, stored, ttl = spy_cache.set_calls[0]
    assert key == "macro:T10Y2Y"
    assert stored == value
    assert ttl == 60


def test_no_partial_failure_key_treated_as_clean__plan_7_2(spy_cache):
    """partial_failure 키가 아예 없으면 clean으로 간주해 저장한다."""
    value = {"data": 1}
    cached = cache_if_clean(spy_cache, "stock:meta:005930", value, ttl_seconds=60)
    assert cached is True
    assert len(spy_cache.set_calls) == 1


def test_cache_if_clean_rejects_forbidden_key__plan_7_1(spy_cache):
    """cache_if_clean도 금지 프리픽스는 정책으로 거부한다(이중 방어)."""
    value = {"partial_failure": []}
    with pytest.raises(CachePolicyError):
        cache_if_clean(spy_cache, "stock:price:005930", value, ttl_seconds=60)
    assert spy_cache.set_calls == []
