"""캐시 정책 3원칙 강제 — plan §4, kis-data-pipeline 스킬 §3.

원칙1: 현재가·등락률 캐시 금지. 허용 프리픽스 화이트리스트 외에는
       is_cacheable가 CachePolicyError로 거부한다(현재가는 stock:price:).
원칙2: 실패 응답 캐시 금지. cache_if_clean은 value["partial_failure"]가
       비어있지 않으면 set을 생략한다.
원칙3(P2, 프리웜): 인터페이스만 — 본 모듈 범위 밖.
"""
from __future__ import annotations

from typing import Any

from cache.base import Cache

# 캐시가 허용되는 네임스페이스 화이트리스트.
# 현재가(stock:price:)는 목록에 없으므로 자동 거부된다.
ALLOWED_PREFIXES = (
    "macro:",       # 매크로 지표 (지표 갱신 주기 TTL)
    "stock:meta:",  # 섹터·상장주식수 등 메타 (수 시간 TTL)
    "kis:token:",   # 인증 토큰 영속
)


class CachePolicyError(RuntimeError):
    """캐시 정책 위반 — 금지된 키를 저장하려 할 때 발생."""


def is_cacheable(key: str) -> bool:
    """키가 캐시 허용 네임스페이스에 속하는지 검사.

    허용되면 True, 금지 프리픽스면 CachePolicyError를 던진다(조용한
    실패로 넘어가지 않게 한다).
    """
    if any(key.startswith(prefix) for prefix in ALLOWED_PREFIXES):
        return True
    raise CachePolicyError(
        f"캐시 금지 키: {key!r} — 허용 프리픽스 {ALLOWED_PREFIXES} 만 저장 가능 "
        "(현재가·등락률은 캐시 금지, 원칙1)"
    )


def cache_if_clean(cache: Cache, key: str, value: Any, ttl_seconds: int) -> bool:
    """실패가 섞이지 않은 응답만 캐시에 저장한다(원칙2).

    - 금지 프리픽스면 CachePolicyError(원칙1, 이중 방어).
    - value["partial_failure"]가 비어있지 않으면 set을 생략하고 False 반환.
    - 저장하면 True 반환.
    """
    is_cacheable(key)  # 원칙1 가드 — 위반 시 CachePolicyError

    partial_failure = value.get("partial_failure") if isinstance(value, dict) else None
    if partial_failure:
        return False

    cache.set(key, value, ttl_seconds)
    return True
