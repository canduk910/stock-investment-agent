"""JSON 파일 원자적 read/write + in-process 락 — durable store 공용 헬퍼(IMP-13).

watchlist/store.py 와 chat/report_store.py 가 바이트 동일한 _read_raw/_write_raw 를 각자
갖고 있던 것을 이 한 곳으로 모은다(원자적 write·손상 방어 수정이 한 곳에만 퍼지게).
상위 계약(list_items/put vs append/list_history)은 각 store 가 유지하고, 디스크 I/O 만 공유한다.

주의: 이건 캐시가 아니라 durable 사용자 상태/산출물이다(캐시 3원칙 무관). read-modify-write 는
lock() 컨텍스트로 임계영역을 감싼다 — in-process 경합만 막는다(다중 프로세스는 분산 락/DynamoDB
conditional write 필요). FileCache(cache/local.py)의 의도적 비원자성과는 별개다.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path


class AtomicJsonFile:
    """JSON 파일의 원자적 read/write + 공유 락. store 가 has-a 로 재사용."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()

    def lock(self) -> threading.Lock:
        """read-modify-write 임계영역 보호용 락(`with file.lock(): ...`)."""
        return self._lock

    def read(self) -> dict:
        """디스크 → dict. 부재·손상(JSON 깨짐)·비-dict 는 빈 dict(graceful, FileCache 관례)."""
        if not self._path.exists():
            return {}
        try:
            with self._path.open(encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def write(self, data: dict) -> None:
        """원자적 write: 같은 디렉토리 temp 파일에 쓰고 os.replace 로 교체(부분 쓰기 방지)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(f"{self._path.name}.tmp.{os.getpid()}")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, self._path)  # 원자적 교체(동일 파일시스템)
