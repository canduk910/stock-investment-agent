"""캐시 통합 배선 — plan §4, T8.

메타(stock:meta:)·매크로(macro:) 등 캐시 허용 데이터를 get_or_fetch 하나로
읽는다. 저장은 반드시 policy.cache_if_clean을 경유하므로 3원칙이 강제된다:
- 금지 프리픽스(현재가 등)면 CachePolicyError (원칙1)
- partial_failure 섞인 응답은 저장 생략 → 다음 요청이 재시도 (원칙2)

현재가 경로는 이 헬퍼를 쓰지 않는다(어댑터에 캐시 자체가 없음).
"""
from __future__ import annotations

from typing import Any, Callable

from cache.base import Cache
from cache.policy import cache_if_clean


def get_or_fetch(
    cache: Cache,
    key: str,
    fetch: Callable[[], Any],
    ttl_seconds: int,
) -> Any:
    """캐시 히트면 반환, 아니면 fetch 후 정책을 통과한 경우에만 저장."""
    cached = cache.get(key)
    if cached is not None:
        return cached

    value = fetch()
    cache_if_clean(cache, key, value, ttl_seconds)  # 원칙1/2 강제
    return value
