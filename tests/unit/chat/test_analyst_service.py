"""수집→요약→저장 오케스트레이션 — idempotent·병렬·graceful(수집·다운로드·요약 mock)."""
from __future__ import annotations

import uuid

import chat.analyst_report as analyst_report
import chat.analyst_service as svc
import collectors.naver_research as naver_research
import rag.ingest as ingest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from chat.analyst_store import AnalystReportStore
from infra.db import Base, import_models


def _sql_store(tmp_path=None):
    """SQL 공동 DB 백엔드의 애널리스트 store(격리된 새 엔진).

    **파일 SQLite**(인메모리 StaticPool 아님) — service 가 ThreadPool 로 병렬 upsert 하므로
    워커마다 자기 커넥션(프로덕션 Postgres/파일 SQLite 와 동일한 풀 동작)이어야 경합이 안 난다.
    인메모리+StaticPool 은 단일 커넥션 공유라 동시 쓰기에서 flaky. busy_timeout 으로 락 대기.
    """
    import_models()
    import tempfile

    base = tmp_path or tempfile.mkdtemp()
    db_path = f"{base}/analyst-{uuid.uuid4().hex}.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
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
    store = _sql_store(str(tmp_path))
    out = svc.fetch_and_summarize(limit=10, store=store)
    assert out == {"fetched": 2, "new": 2, "skipped": 0, "failed": 0}
    assert len(store.list_reports("006360")) == 1
    assert len(store.list_reports("000660")) == 1


def test_fetch_idempotent_second_run(monkeypatch, tmp_path):
    _patch_pipeline(monkeypatch)
    store = _sql_store(str(tmp_path))
    svc.fetch_and_summarize(limit=10, store=store)
    out = svc.fetch_and_summarize(limit=10, store=store)  # 재실행 → 전부 skip
    assert out["new"] == 0 and out["skipped"] == 2


def test_fetch_summary_failure_counts_failed(monkeypatch, tmp_path):
    _patch_pipeline(monkeypatch, summary_ok=False)
    store = _sql_store(str(tmp_path))
    out = svc.fetch_and_summarize(limit=10, store=store)
    assert out["failed"] == 2 and out["new"] == 0
    assert store.list_reports("006360") == []  # 실패는 저장 안 함


def test_fetch_download_failure_graceful(monkeypatch, tmp_path):
    _patch_pipeline(monkeypatch)
    monkeypatch.setattr(naver_research, "download_pdf", lambda url, **k: None)  # 다운로드 실패
    store = _sql_store(str(tmp_path))
    out = svc.fetch_and_summarize(limit=10, store=store)
    assert out["failed"] == 2


def test_fetch_empty_feed(monkeypatch, tmp_path):
    monkeypatch.setattr(naver_research, "fetch_company_reports", lambda limit: [])
    store = _sql_store(str(tmp_path))
    out = svc.fetch_and_summarize(limit=10, store=store)
    assert out == {"fetched": 0, "new": 0, "skipped": 0, "failed": 0}


# ── 종목별 수집(itemCode) — fetch_stock_reports 경유, 그 종목만 저장 ──
def test_fetch_for_ticker_uses_stock_feed(monkeypatch, tmp_path):
    captured = {}

    def _fetch_stock(ticker, limit):
        captured["ticker"] = ticker
        captured["limit"] = limit
        return [_METAS[0]]  # 006360 한 건만(그 종목 필터 결과)

    monkeypatch.setattr(naver_research, "fetch_stock_reports", _fetch_stock)
    monkeypatch.setattr(naver_research, "download_pdf", lambda url, **k: "/tmp/f.pdf")
    monkeypatch.setattr(ingest, "extract_text", lambda path: "리포트 원문")
    monkeypatch.setattr(
        analyst_report, "summarize_report",
        lambda text, meta, client=None: {
            "summary": {"증권사": meta["broker"]}, "validation_failed": False
        },
    )
    store = _sql_store(str(tmp_path))
    out = svc.fetch_and_summarize_for_ticker("006360", limit=7, store=store)
    assert out == {"fetched": 1, "new": 1, "skipped": 0, "failed": 0}
    # 종목별 피드(전체 최신 피드 아님)를 그 ticker·limit 로 호출했는가
    assert captured == {"ticker": "006360", "limit": 7}
    assert len(store.list_reports("006360")) == 1
    assert store.list_reports("000660") == []  # 다른 종목은 안 섞임


def test_fetch_for_ticker_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(naver_research, "fetch_stock_reports", lambda ticker, limit: [])
    store = _sql_store(str(tmp_path))
    out = svc.fetch_and_summarize_for_ticker("006360", limit=10, store=store)
    assert out == {"fetched": 0, "new": 0, "skipped": 0, "failed": 0}


def test_fetch_missing_code_or_nid_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(
        naver_research, "fetch_company_reports",
        lambda limit: [{"stock_code": "", "nid": "1", "pdf_url": "https://x/1.pdf"}],
    )
    monkeypatch.setattr(naver_research, "download_pdf", lambda url, **k: "/tmp/f.pdf")
    monkeypatch.setattr(ingest, "extract_text", lambda path: "x")
    store = _sql_store(str(tmp_path))
    out = svc.fetch_and_summarize(limit=10, store=store)
    assert out["failed"] == 1
