"""시황(market outlook) 요약 저장소 — 단일 스코프 flat 리스트·idempotent(analyst_store 패턴).

시황은 시장 전체라 종목(ticker)이 없다 → analyst_store 처럼 ticker 키가 아니라 단일 리스트로 둔다.
disk: {"reports": [{report_id, broker, title, date, pdf_url, summary, created_at}, ...]}.
report_id(네이버 nid) 중복이면 재요약하지 않는다(반복 fetch 비용·중복 방지). 리포트=정적 문서라
캐시 허용(원칙1 무관)이나 저작물 → PDF·이 파일은 gitignore(.cache/). Phase 5 에서 공동 DB 이전.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from infra.json_store import AtomicJsonFile

MARKET_OUTLOOK_STORE_PATH = ".cache/market_outlook.json"
MARKET_OUTLOOK_CAP = 30  # 무한 누적 방지
_KEY = "reports"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MarketOutlookStore:
    """JSON 파일 store — 원자적 write + 락, 시황 요약 flat 리스트."""

    def __init__(self, path: str | Path = MARKET_OUTLOOK_STORE_PATH) -> None:
        self._file = AtomicJsonFile(path)

    def has(self, report_id) -> bool:
        with self._file.lock():
            raw = self._file.read()
        return any(e.get("report_id") == report_id for e in raw.get(_KEY, []))

    def upsert(self, entry: dict) -> bool:
        """report_id 중복이면 skip(False), 새로 추가하면 True. created_at 자동."""
        rid = entry.get("report_id")
        with self._file.lock():
            raw = self._file.read()
            lst = raw.setdefault(_KEY, [])
            if rid is not None and any(e.get("report_id") == rid for e in lst):
                return False
            entry.setdefault("created_at", _now_iso())
            lst.append(entry)
            if len(lst) > MARKET_OUTLOOK_CAP:
                lst.sort(key=lambda e: e.get("created_at", ""))
                raw[_KEY] = lst[-MARKET_OUTLOOK_CAP:]
            self._file.write(raw)
        return True

    def list_reports(self) -> list[dict]:
        """시황 요약 리스트(작성일 내림차순 — 최신 우선). 없으면 빈 리스트."""
        with self._file.lock():
            raw = self._file.read()
        return sorted(list(raw.get(_KEY, [])), key=lambda e: e.get("date", ""), reverse=True)


_default: MarketOutlookStore | None = None


def default_store() -> MarketOutlookStore:
    global _default
    if _default is None:
        _default = MarketOutlookStore()
    return _default
