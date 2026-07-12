"""수집→요약→저장 오케스트레이션 — idempotent·병렬·graceful(수집·다운로드·요약 mock)."""
from __future__ import annotations

import chat.analyst_report as analyst_report
import chat.analyst_service as svc
import collectors.naver_research as naver_research
import rag.ingest as ingest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from chat.analyst_store import AnalystReportStore
from infra.db import Base, import_models


def _sql_store():
    """SQL 공동 DB(인메모리) 백엔드의 애널리스트 store(격리된 새 엔진)."""
    import_models()
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False)
    return AnalystReportStore(session_factory=sf)

_METAS = [
    {"stock_code": "006360", "nid": "1", "stock_name": "GS건설", "broker": "한화",
     "title": "t1", "date": "26.07.10", "pdf_url": "https://x/1.pdf"},
    {"stock_code": "000660", "nid": "2", "stock_name": "SK하이닉스", "broker": "미래",
     "title": "t2", "date": "26.07.10", "pdf_url": "https://x/2.pdf"},
]


def _patch_pipeline(monkeypatch, *, summary_ok=True):
    monkeypatch.setattr(naver_research, "fetch_company_reports", lambda limit: list(_METAS))
    monkeypatch.setattr(naver_research, "download_pdf", lambda url, **k: "/tmp/fake.pdf")
    monkeypatch.setattr(ingest, "extract_text", lambda path: "리포트 원문")
    monkeypatch.setattr(
        analyst_report, "summarize_report",
        lambda text, meta, client=None: (
            {"summary": {"증권사": meta["broker"], "종목": meta["stock_name"]}, "validation_failed": False}
            if summary_ok else {"summary": None, "validation_failed": True}
        ),
    )


def test_fetch_and_summarize_stores_all(monkeypatch, tmp_path):
    _patch_pipeline(monkeypatch)
    store = _sql_store()
    out = svc.fetch_and_summarize(limit=10, store=store)
    assert out == {"fetched": 2, "new": 2, "skipped": 0, "failed": 0}
    assert len(store.list_reports("006360")) == 1
    assert len(store.list_reports("000660")) == 1


def test_fetch_idempotent_second_run(monkeypatch, tmp_path):
    _patch_pipeline(monkeypatch)
    store = _sql_store()
    svc.fetch_and_summarize(limit=10, store=store)
    out = svc.fetch_and_summarize(limit=10, store=store)  # 재실행 → 전부 skip
    assert out["new"] == 0 and out["skipped"] == 2


def test_fetch_summary_failure_counts_failed(monkeypatch, tmp_path):
    _patch_pipeline(monkeypatch, summary_ok=False)
    store = _sql_store()
    out = svc.fetch_and_summarize(limit=10, store=store)
    assert out["failed"] == 2 and out["new"] == 0
    assert store.list_reports("006360") == []  # 실패는 저장 안 함


def test_fetch_download_failure_graceful(monkeypatch, tmp_path):
    _patch_pipeline(monkeypatch)
    monkeypatch.setattr(naver_research, "download_pdf", lambda url, **k: None)  # 다운로드 실패
    store = _sql_store()
    out = svc.fetch_and_summarize(limit=10, store=store)
    assert out["failed"] == 2


def test_fetch_empty_feed(monkeypatch, tmp_path):
    monkeypatch.setattr(naver_research, "fetch_company_reports", lambda limit: [])
    store = _sql_store()
    out = svc.fetch_and_summarize(limit=10, store=store)
    assert out == {"fetched": 0, "new": 0, "skipped": 0, "failed": 0}


def test_fetch_missing_code_or_nid_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(
        naver_research, "fetch_company_reports",
        lambda limit: [{"stock_code": "", "nid": "1", "pdf_url": "https://x/1.pdf"}],
    )
    monkeypatch.setattr(naver_research, "download_pdf", lambda url, **k: "/tmp/f.pdf")
    monkeypatch.setattr(ingest, "extract_text", lambda path: "x")
    store = _sql_store()
    out = svc.fetch_and_summarize(limit=10, store=store)
    assert out["failed"] == 1
