"""로컬 캐시 구현 — plan §4.

LocalCache: dict 기반, TTL 만료. 프로세스 수명 동안 유효.
FileCache: JSON 파일 영속 — 인증 토큰을 재실행/재발급 없이 재사용(스킬 §1.3).

둘 다 cache.base.Cache 시그니처를 따른다(문자열 키 + ttl_seconds).
clock 주입으로 TTL을 결정적으로 테스트한다.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable


class LocalCache:
    """dict + TTL 인메모리 캐시."""

    def __init__(self, clock: Callable[[], float] = time.time):
        self._clock = clock
        self._store: dict[str, tuple[float, Any]] = {}  # key -> (expire_at, value)

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expire_at, value = entry
        if self._clock() >= expire_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._store[key] = (self._clock() + ttl_seconds, value)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)


class FileCache:
    """JSON 파일 영속 캐시 — 토큰처럼 프로세스 재실행에도 유지돼야 하는 값용."""

    def __init__(self, path: str | Path, clock: Callable[[], float] = time.time):
        self._path = Path(path)
        self._clock = clock

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            with self._path.open(encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def get(self, key: str) -> Any | None:
        data = self._read()
        entry = data.get(key)
        if entry is None:
            return None
        if self._clock() >= entry["expire_at"]:
            data.pop(key, None)
            self._write(data)
            return None
        return entry["value"]

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        data = self._read()
        data[key] = {"expire_at": self._clock() + ttl_seconds, "value": value}
        self._write(data)

    def delete(self, key: str) -> None:
        data = self._read()
        if data.pop(key, None) is not None:
            self._write(data)
