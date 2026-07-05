"""추상 캐시 인터페이스 — plan §4.

로컬 개발은 dict/파일 캐시로 시작하되, 시그니처는 ElastiCache/DynamoDB
호환으로 고정한다(문자열 키 + TTL). 로직은 인터페이스에만 의존한다.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Cache(Protocol):
    def get(self, key: str) -> Any | None: ...

    def set(self, key: str, value: Any, ttl_seconds: int) -> None: ...

    def delete(self, key: str) -> None: ...
