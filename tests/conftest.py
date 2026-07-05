"""공용 pytest fixture — 기록된 실제 응답 로더, mock 캐시.

TDD 원칙(tdd-workflow): mock 반환 shape은 반드시 기록된 실제 응답(fixtures/)에서 취득한다.
손으로 지어낸 mock 응답은 경계면 버그를 숨긴다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture():
    """tests/fixtures/{name}.json 을 dict로 로드."""

    def _load(name: str):
        path = FIXTURES_DIR / f"{name}.json"
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    return _load


class SpyCache:
    """set 호출을 기록하는 테스트용 캐시 — 캐시 정책 검증에 사용.

    실제 저장소가 아니라 경계(cache) mock. 캐시 3원칙 테스트가
    'set이 호출됐는가/안 됐는가'를 이 spy로 확인한다.
    """

    def __init__(self):
        self.store: dict = {}
        self.set_calls: list[tuple] = []

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value, ttl_seconds: int) -> None:
        self.set_calls.append((key, value, ttl_seconds))
        self.store[key] = value

    def delete(self, key: str) -> None:
        self.store.pop(key, None)


@pytest.fixture
def spy_cache():
    return SpyCache()
