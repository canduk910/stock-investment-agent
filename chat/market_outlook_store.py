"""시황(market outlook) 요약 저장소 — **공동 DB(전역 공유)**, 단일 스코프(__MARKET__).

Phase 5: JSON 파일(.cache) → SQL 공동 테이블(AnalystReportRow, scope_key=__MARKET__) 이전.
시황은 시장 전체라 종목(ticker)이 없어 단일 스코프에 flat 저장한다. 인터페이스(has/upsert/
list_reports)는 그대로라 라우트·서비스 무변경. report_id(nid) 중복 skip(idempotent).
"""
from __future__ import annotations

from chat.report_models import MARKET_SCOPE
from chat.report_repo import ScopedReportRepo


class MarketOutlookStore:
    """시황(__MARKET__) 스코프 공동 저장소(SQL 백엔드). ticker 없음."""

    def __init__(self, session_factory=None) -> None:
        self._repo = ScopedReportRepo(session_factory)

    def has(self, report_id) -> bool:
        return self._repo.has(MARKET_SCOPE, report_id)

    def upsert(self, entry: dict) -> bool:
        return self._repo.upsert(MARKET_SCOPE, entry)

    def list_reports(self) -> list[dict]:
        return self._repo.list_reports(MARKET_SCOPE)

    def get(self, report_id) -> dict | None:
        """report_id 단건 조회(챗 상담 컨텍스트용). 없으면 None. ticker 없음(시장 전체)."""
        return self._repo.get(MARKET_SCOPE, report_id)


_default: MarketOutlookStore | None = None


def default_store() -> MarketOutlookStore:
    global _default
    if _default is None:
        _default = MarketOutlookStore()
    return _default
