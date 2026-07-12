"""공동 리포트 저장소 코어 — scope_key(ticker | __MARKET__)로 묶인 전역 공유 요약(AnalystReportRow).

analyst_store·market_outlook_store 가 이걸 감싼다(같은 인터페이스 유지 → 라우트·서비스 무변경).
db 미주입 시 메서드마다 짧은 세션을 연다(전역 공유 데이터라 요청 스코프 불필요). 테스트는 db 주입.
list 는 작성일(date 문자열 YY.MM.DD) 내림차순 = 기존 JSON store 와 동일 semantics.
"""
from __future__ import annotations

from sqlalchemy import select

from chat.report_models import AnalystReportRow, _utcnow
from infra.db import get_sessionmaker


def _entry_from_row(row: AnalystReportRow) -> dict:
    """Row → 기존 JSON store 와 동일한 entry dict(프론트·소비 계약 불변)."""
    return {
        "report_id": row.report_id,
        "broker": row.broker,
        "stock_name": row.stock_name,
        "title": row.title,
        "date": row.date,
        "pdf_url": row.pdf_url,
        "summary": row.summary_json,
        "created_at": row.created_at.isoformat(),
    }


class ScopedReportRepo:
    """세션 팩토리를 받아 **메서드마다 새 세션**을 연다(스레드 안전 — 병렬 수집에서 각 스레드가
    자기 세션). session_factory 미주입 시 앱 기본(get_sessionmaker). 테스트는 인메모리 엔진
    바인딩 sessionmaker 를 주입(StaticPool 로 같은 DB 공유)."""

    def __init__(self, session_factory=None) -> None:
        self._sf = session_factory

    def _run(self, fn):
        factory = self._sf or get_sessionmaker()
        db = factory()
        try:
            return fn(db)
        finally:
            db.close()

    def _find(self, db, scope_key, report_id):
        return db.scalar(
            select(AnalystReportRow).where(
                AnalystReportRow.scope_key == scope_key,
                AnalystReportRow.report_id == str(report_id),
            )
        )

    def has(self, scope_key: str, report_id) -> bool:
        return self._run(lambda db: self._find(db, scope_key, report_id) is not None)

    def upsert(self, scope_key: str, entry: dict) -> bool:
        """report_id 중복이면 skip(False), 새로 추가하면 True(idempotent)."""
        rid = entry.get("report_id")

        def _op(db):
            if rid is not None and self._find(db, scope_key, rid) is not None:
                return False
            db.add(
                AnalystReportRow(
                    scope_key=scope_key,
                    report_id=str(rid),
                    broker=entry.get("broker"),
                    stock_name=entry.get("stock_name"),
                    title=entry.get("title"),
                    date=entry.get("date"),
                    pdf_url=entry.get("pdf_url"),
                    summary_json=entry.get("summary") or {},
                    created_at=_utcnow(),
                )
            )
            db.commit()
            return True

        return self._run(_op)

    def list_reports(self, scope_key: str) -> list[dict]:
        def _op(db):
            rows = db.scalars(
                select(AnalystReportRow)
                .where(AnalystReportRow.scope_key == scope_key)
                .order_by(AnalystReportRow.date.desc())
            ).all()
            return [_entry_from_row(r) for r in rows]

        return self._run(_op)

    def get(self, scope_key: str, report_id) -> dict | None:
        def _op(db):
            row = self._find(db, scope_key, report_id)
            return _entry_from_row(row) if row else None

        return self._run(_op)
