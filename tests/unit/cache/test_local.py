"""로컬 캐시 구현 테스트 — plan §4.

LocalCache(dict+TTL): get/set/delete + 만료.
FileCache: 토큰 영속(재실행에도 유지) — ElastiCache/DynamoDB 호환 시그니처.
"""
from __future__ import annotations

from cache.local import FileCache, LocalCache


def test_local_cache_get_set():
    c = LocalCache()
    assert c.get("k") is None
    c.set("k", {"v": 1}, ttl_seconds=60)
    assert c.get("k") == {"v": 1}


def test_local_cache_delete():
    c = LocalCache()
    c.set("k", 1, ttl_seconds=60)
    c.delete("k")
    assert c.get("k") is None


def test_local_cache_ttl_expiry():
    """TTL 경과 시 get은 None을 반환(만료)."""
    now = {"t": 1000.0}
    c = LocalCache(clock=lambda: now["t"])
    c.set("k", "v", ttl_seconds=10)
    now["t"] = 1005.0
    assert c.get("k") == "v"  # 아직 유효
    now["t"] = 1011.0
    assert c.get("k") is None  # 만료


def test_file_cache_persists_across_instances(tmp_path):
    """FileCache는 파일에 영속 — 새 인스턴스에서도 값을 읽는다(토큰 재사용)."""
    path = tmp_path / "cache.json"
    c1 = FileCache(path)
    c1.set("kis:token:real", {"token": "abc"}, ttl_seconds=3600)
    c2 = FileCache(path)
    assert c2.get("kis:token:real") == {"token": "abc"}


def test_file_cache_ttl_expiry(tmp_path):
    now = {"t": 1000.0}
    path = tmp_path / "cache.json"
    c = FileCache(path, clock=lambda: now["t"])
    c.set("k", "v", ttl_seconds=10)
    now["t"] = 1011.0
    assert c.get("k") is None
