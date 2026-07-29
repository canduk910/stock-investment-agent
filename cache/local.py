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
        # clock 주입 — 테스트가 가짜 시계를 넣어 TTL 만료를 결정적으로 재현(실시간 sleep 불요).
        self._clock = clock
        self._store: dict[str, tuple[float, Any]] = {}  # key -> (expire_at, value)

    def get(self, key: str) -> Any | None:
        """키 값 반환. 없거나 TTL 만료면 None(만료 항목은 조회 시 lazy 하게 제거)."""
        entry = self._store.get(key)
        if entry is None:
            return None
        expire_at, value = entry
        # 만료 시각을 넘겼으면 제거하고 miss 로 취급(별도 정리 스레드 없이 lazy expiry).
        if self._clock() >= expire_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        # 절대 만료 시각 = 현재 + TTL 로 저장(get 시 이 시각과 비교).
        self._store[key] = (self._clock() + ttl_seconds, value)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)


class FileCache:
    """JSON 파일 영속 캐시 — 토큰처럼 프로세스 재실행에도 유지돼야 하는 값용."""

    def __init__(self, path: str | Path, clock: Callable[[], float] = time.time):
        self._path = Path(path)
        self._clock = clock

    def _read(self) -> dict[str, Any]:
        """파일 전체를 dict 로 로드. 파일 없음·깨진 JSON·읽기 오류는 빈 dict(캐시 miss 로 안전 강등)."""
        if not self._path.exists():
            return {}
        try:
            with self._path.open(encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            # 손상된 캐시 파일이 앱을 죽이면 안 된다 — 빈 캐시로 취급하고 다음 set 에서 재생성.
            return {}

    def _write(self, data: dict[str, Any]) -> None:
        # 상위 디렉토리(.cache 등)가 없을 수 있으니 먼저 생성. ensure_ascii=False 로 한글 원문 저장.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def get(self, key: str) -> Any | None:
        """키 값 반환. 없거나 TTL 만료면 None. 만료 항목은 파일에서 제거 후 재기록."""
        data = self._read()
        entry = data.get(key)
        if entry is None:
            return None
        # 만료면 해당 키만 지우고 파일을 갱신(다음 조회부터 miss).
        if self._clock() >= entry["expire_at"]:
            data.pop(key, None)
            self._write(data)
            return None
        return entry["value"]

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        # read-modify-write: 기존 파일을 읽어 이 키만 갱신(다른 키 보존) 후 전체 재기록.
        data = self._read()
        data[key] = {"expire_at": self._clock() + ttl_seconds, "value": value}
        self._write(data)

    def delete(self, key: str) -> None:
        # 실제로 지운 게 있을 때만 파일을 다시 쓴다(불필요한 디스크 쓰기 방지).
        data = self._read()
        if data.pop(key, None) is not None:
            self._write(data)
