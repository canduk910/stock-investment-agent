"""애널리스트 리포트 요약 저장소 — **공동 DB(전역 공유, user 무관)**, ticker 키.

Phase 5: JSON 파일(.cache) → SQL 공동 테이블(AnalystReportRow, scope_key=ticker) 이전.
인터페이스(has/upsert/list_reports/get)는 그대로라 라우트·서비스·view_context 무변경.
report_id(nid) 중복이면 재요약하지 않는다(idempotent). 요약=리포트 인용(에이전트 판정 아님).
"""
from __future__ import annotations

from chat.report_repo import ScopedReportRepo


class AnalystReportStore:
    """ticker 스코프 공동 리포트 저장소(SQL 백엔드). db 미주입 시 메서드마다 새 세션."""

    def __init__(self, session_factory=None) -> None:
        self._repo = ScopedReportRepo(session_factory)

    def has(self, ticker: str, report_id) -> bool:
        return self._repo.has(ticker, report_id)

    def upsert(self, ticker: str, entry: dict) -> bool:
        return self._repo.upsert(ticker, entry)

    def list_reports(self, ticker: str) -> list[dict]:
        return self._repo.list_reports(ticker)

    def get(self, ticker: str, report_id) -> dict | None:
        return self._repo.get(ticker, report_id)


_default: AnalystReportStore | None = None


def default_store() -> AnalystReportStore:
    global _default
    if _default is None:
        _default = AnalystReportStore()
    return _default
