"""애널리스트 리포트 요약 저장소 — ticker 키·idempotent(report_store.py 패턴 재사용).

디스크: {ticker: [{report_id, broker, title, date, pdf_url, summary, created_at}, ...]}.
report_id(네이버 nid) 중복이면 재요약하지 않는다(idempotent — 반복 fetch 비용·중복 방지).
리포트는 정적 문서라 캐시 허용(원칙1 무관)이나 저작물 → PDF·이 파일은 gitignore(.cache/).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from infra.json_store import AtomicJsonFile

ANALYST_STORE_PATH = ".cache/analyst_reports.json"
ANALYST_CAP = 20  # ticker 당 상한(무한 누적 방지)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AnalystReportStore:
    """JSON 파일 store — 원자적 write + 락, ticker 별 리포트 요약 리스트."""

    def __init__(self, path: str | Path = ANALYST_STORE_PATH) -> None:
        self._file = AtomicJsonFile(path)

    def has(self, ticker: str, report_id) -> bool:
        with self._file.lock():
            raw = self._file.read()
        return any(e.get("report_id") == report_id for e in raw.get(ticker, []))

    def upsert(self, ticker: str, entry: dict) -> bool:
        """report_id 중복이면 skip(False), 새로 추가하면 True. created_at 자동."""
        rid = entry.get("report_id")
        with self._file.lock():
            raw = self._file.read()
            lst = raw.setdefault(ticker, [])
            if rid is not None and any(e.get("report_id") == rid for e in lst):
                return False
            entry.setdefault("created_at", _now_iso())
            lst.append(entry)
            if len(lst) > ANALYST_CAP:
                lst.sort(key=lambda e: e.get("created_at", ""))
                raw[ticker] = lst[-ANALYST_CAP:]
            self._file.write(raw)
        return True

    def list_reports(self, ticker: str) -> list[dict]:
        """ticker 의 리포트 요약 리스트(작성일 내림차순 — 최신 우선). 없으면 빈 리스트."""
        with self._file.lock():
            raw = self._file.read()
        return sorted(list(raw.get(ticker, [])), key=lambda e: e.get("date", ""), reverse=True)

    def get(self, ticker: str, report_id) -> dict | None:
        """ticker·report_id 로 단일 리포트 entry 조회(챗 상담 컨텍스트용). 없으면 None."""
        with self._file.lock():
            raw = self._file.read()
        for e in raw.get(ticker, []):
            if e.get("report_id") == report_id:
                return e
        return None


_default: AnalystReportStore | None = None


def default_store() -> AnalystReportStore:
    global _default
    if _default is None:
        _default = AnalystReportStore()
    return _default
