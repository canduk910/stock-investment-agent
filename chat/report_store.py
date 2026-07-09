"""리포트 히스토리 저장소 — plan §"chat/report_store.py" (P2).

watchlist/store.py 와 동일 JSON-파일 패턴(원자적 write=temp+os.replace + threading.Lock).
차이: 여기는 (ticker, created_at) 키의 append-only 히스토리다 — 같은 종목을 시점을 달리해
여러 번 평가하고 과거 평가와 비교하는 데모(§6.5b). 캐시가 아니라 durable 산출물이므로
캐시 3원칙과 무관하지만 파일은 .cache/ 관례에 둔다(kis_token·stock_master 와 나란히).

디스크 구조: {ticker: [ {created_at, regime_at_creation, report_json}, ... ]}.
list_history 는 created_at 내림차순(최신 우선)으로 반환한다.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

# 히스토리 파일 기본 경로(watchlist.json 과 나란히 .cache/ 아래).
REPORT_STORE_PATH = ".cache/stock_reports.json"


def _now_iso() -> str:
    """현재 UTC ISO8601(created_at 자동 생성)."""
    return datetime.now(timezone.utc).isoformat()


class JsonFileReportStore:
    """JSON 파일 append-only 히스토리 — 원자적 write + threading.Lock."""

    def __init__(self, path: str | Path = REPORT_STORE_PATH) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()

    # ── 디스크 I/O ────────────────────────────────────────────────────────────

    def _read_raw(self) -> dict[str, list[dict]]:
        """디스크 → {ticker: [entry, ...]}. 부재·손상은 빈 dict(FileCache 관례)."""
        if not self._path.exists():
            return {}
        try:
            with self._path.open(encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_raw(self, data: dict[str, list[dict]]) -> None:
        """원자적 write: 같은 디렉토리 temp 파일에 쓰고 os.replace 로 교체(부분 쓰기 방지)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(f"{self._path.name}.tmp.{os.getpid()}")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, self._path)  # 원자적 교체(동일 파일시스템)

    # ── 계약 ─────────────────────────────────────────────────────────────────

    def append(
        self,
        ticker: str,
        report_json: dict,
        *,
        regime_at_creation: str | None,
        created_at: str | None = None,
    ) -> dict:
        """평가 1건을 ticker 히스토리에 추가하고 저장된 entry 를 반환.

        created_at 미전달 시 현재 UTC 로 자동 생성. report_json 은 StockReport.model_dump()
        결과(한글 키). regime_at_creation 은 생성 시점 국면(과거 평가 비교의 맥락).
        """
        entry = {
            "created_at": created_at or _now_iso(),
            "regime_at_creation": regime_at_creation,
            "report_json": report_json,
        }
        with self._lock:
            raw = self._read_raw()
            raw.setdefault(ticker, []).append(entry)
            self._write_raw(raw)
        return entry

    def list_history(self, ticker: str) -> list[dict]:
        """ticker 의 평가 히스토리(created_at 내림차순 — 최신 우선). 없으면 빈 리스트."""
        with self._lock:
            raw = self._read_raw()
        entries = list(raw.get(ticker, []))
        return sorted(entries, key=lambda e: e.get("created_at", ""), reverse=True)
