"""워치리스트 저장소 — plan §"watchlist/store.py"·§5(스왑 가능 Store).

cache/base.py Protocol 정신: 스왑 가능한 인터페이스 + 로컬 파일 구현 + 인메모리(테스트).
캐시가 아니라 durable 사용자 상태다 → 캐시 3원칙과 무관(현재가 캐시 금지는 시세 경로,
여기는 사용자가 등록한 종목·목표가). 키 (user_id, ticker) = DynamoDB PK/SK 계약.

JsonFileWatchlistStore:
- 원자적 write(temp + os.replace) — 중간 쓰기 손상 방지.
- in-process threading.Lock — 동시 요청 read-modify-write 경합 차단(다중 프로세스는
  분산 락 필요, 클라우드 전환 시 DynamoDB conditional write 로 대체).
- upsert 는 added_at 을 최초값으로 보존(중복 추가 = 갱신, 재등록 시각으로 밀리지 않게).
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from infra.json_store import AtomicJsonFile
from watchlist.models import WatchlistItem

# 부분 갱신 sentinel — 목표가 필드 '미제공(변경 안 함)'을 None(해제)과 구분한다.
# 예: PATCH 가 매도 목표가만 보내면 매수 목표가는 _UNSET → 그대로 둔다.
_UNSET = object()


class WatchlistStore(Protocol):
    """스왑 가능한 저장소 계약(DynamoDB/파일/인메모리 교체는 구현체만)."""

    def list_items(self, user_id: str) -> list[WatchlistItem]: ...

    def get(self, user_id: str, ticker: str) -> WatchlistItem | None: ...

    def put(self, item: WatchlistItem) -> WatchlistItem: ...

    def delete(self, user_id: str, ticker: str) -> None: ...

    def update_targets(
        self,
        user_id: str,
        ticker: str,
        *,
        target_price=_UNSET,
        sell_target_price=_UNSET,
    ) -> WatchlistItem | None:
        """매수/매도 목표가 부분 갱신(sentinel `_UNSET`=변경 안 함, `None`=해제). 미등록→None."""
        ...

    def update_target(
        self, user_id: str, ticker: str, target_price: float | None
    ) -> WatchlistItem | None:
        """(하위호환) 매수 목표가만 갱신 — update_targets 로 위임."""
        ...


def _sorted_by_added_at(items: list[WatchlistItem]) -> list[WatchlistItem]:
    """등록순(added_at 오름차순) — GET 기본 정렬. 프론트가 registered 순을 그대로 소비."""
    return sorted(items, key=lambda i: i.added_at)


def _apply_upsert(existing: WatchlistItem | None, incoming: WatchlistItem) -> WatchlistItem:
    """중복 추가 = 갱신. added_at 은 최초 등록값 보존(재등록 시각으로 밀지 않음)."""
    if existing is None:
        return incoming
    return incoming.model_copy(update={"added_at": existing.added_at})


class InMemoryWatchlistStore:
    """테스트·비영속용. dict[user_id][ticker] = WatchlistItem."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, WatchlistItem]] = {}

    def list_items(self, user_id: str) -> list[WatchlistItem]:
        return _sorted_by_added_at(list(self._data.get(user_id, {}).values()))

    def get(self, user_id: str, ticker: str) -> WatchlistItem | None:
        return self._data.get(user_id, {}).get(ticker)

    def put(self, item: WatchlistItem) -> WatchlistItem:
        bucket = self._data.setdefault(item.user_id, {})
        stored = _apply_upsert(bucket.get(item.ticker), item)
        bucket[item.ticker] = stored
        return stored

    def delete(self, user_id: str, ticker: str) -> None:
        self._data.get(user_id, {}).pop(ticker, None)

    def update_targets(
        self, user_id, ticker, *, target_price=_UNSET, sell_target_price=_UNSET
    ) -> WatchlistItem | None:
        current = self.get(user_id, ticker)
        if current is None:
            return None
        changes = {}
        if target_price is not _UNSET:
            changes["target_price"] = target_price
        if sell_target_price is not _UNSET:
            changes["sell_target_price"] = sell_target_price
        updated = current.model_copy(update=changes)
        self._data[user_id][ticker] = updated
        return updated

    def update_target(
        self, user_id: str, ticker: str, target_price: float | None
    ) -> WatchlistItem | None:
        return self.update_targets(user_id, ticker, target_price=target_price)


class JsonFileWatchlistStore:
    """JSON 파일 영속 — 원자적 write + threading.Lock. 프로세스 재실행에도 유지."""

    def __init__(self, path: str | Path) -> None:
        self._file = AtomicJsonFile(path)  # 원자적 read/write + 락(IMP-13 공용 헬퍼)

    def _bucket_items(self, raw: dict, user_id: str) -> list[WatchlistItem]:
        return [WatchlistItem(**d) for d in raw.get(user_id, {}).values()]

    # ── 계약 ─────────────────────────────────────────────────────────────────

    def list_items(self, user_id: str) -> list[WatchlistItem]:
        with self._file.lock():
            raw = self._file.read()
            return _sorted_by_added_at(self._bucket_items(raw, user_id))

    def get(self, user_id: str, ticker: str) -> WatchlistItem | None:
        with self._file.lock():
            raw = self._file.read()
            d = raw.get(user_id, {}).get(ticker)
            return WatchlistItem(**d) if d else None

    def put(self, item: WatchlistItem) -> WatchlistItem:
        with self._file.lock():
            raw = self._file.read()
            bucket = raw.setdefault(item.user_id, {})
            existing_d = bucket.get(item.ticker)
            existing = WatchlistItem(**existing_d) if existing_d else None
            stored = _apply_upsert(existing, item)
            bucket[item.ticker] = stored.model_dump()
            self._file.write(raw)
            return stored

    def delete(self, user_id: str, ticker: str) -> None:
        with self._file.lock():
            raw = self._file.read()
            bucket = raw.get(user_id)
            if bucket and bucket.pop(ticker, None) is not None:
                self._file.write(raw)

    def update_targets(
        self, user_id, ticker, *, target_price=_UNSET, sell_target_price=_UNSET
    ) -> WatchlistItem | None:
        with self._file.lock():
            raw = self._file.read()
            d = raw.get(user_id, {}).get(ticker)
            if not d:
                return None
            changes = {}
            if target_price is not _UNSET:
                changes["target_price"] = target_price
            if sell_target_price is not _UNSET:
                changes["sell_target_price"] = sell_target_price
            updated = WatchlistItem(**d).model_copy(update=changes)
            raw[user_id][ticker] = updated.model_dump()
            self._file.write(raw)
            return updated

    def update_target(
        self, user_id: str, ticker: str, target_price: float | None
    ) -> WatchlistItem | None:
        return self.update_targets(user_id, ticker, target_price=target_price)
