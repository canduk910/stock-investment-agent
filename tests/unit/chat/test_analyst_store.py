"""애널리스트 요약 store(SQL 공동 DB) — roundtrip·idempotent(report_id)·정렬·종목(scope) 격리."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from chat.analyst_store import AnalystReportStore
from infra.db import Base, import_models


@pytest.fixture
def store():
    import_models()  # AnalystReportRow 등록
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False)
    return AnalystReportStore(session_factory=sf)


def _entry(rid, date="26.07.10", broker="한화투자증권"):
    return {"report_id": rid, "broker": broker, "stock_name": "GS건설", "title": f"리포트{rid}",
            "date": date, "pdf_url": f"https://x/{rid}.pdf",
            "summary": {"증권사": broker, "종목": "GS건설"}}


def test_upsert_and_list(store):
    assert store.upsert("006360", _entry("94082")) is True
    reports = store.list_reports("006360")
    assert len(reports) == 1 and reports[0]["report_id"] == "94082"
    assert reports[0]["created_at"]  # 자동 타임스탬프
    assert reports[0]["summary"] == {"증권사": "한화투자증권", "종목": "GS건설"}


def test_upsert_idempotent_by_report_id(store):
    assert store.upsert("006360", _entry("94082")) is True
    assert store.upsert("006360", _entry("94082")) is False  # 같은 nid → skip
    assert len(store.list_reports("006360")) == 1


def test_has(store):
    store.upsert("006360", _entry("94082"))
    assert store.has("006360", "94082") is True
    assert store.has("006360", "99999") is False
    assert store.has("000660", "94082") is False  # 종목(scope) 분리


def test_list_sorted_by_date_desc(store):
    store.upsert("006360", _entry("1", date="26.07.08"))
    store.upsert("006360", _entry("2", date="26.07.10"))
    store.upsert("006360", _entry("3", date="26.07.09"))
    dates = [r["date"] for r in store.list_reports("006360")]
    assert dates == ["26.07.10", "26.07.09", "26.07.08"]


def test_get_single(store):
    store.upsert("006360", _entry("94082"))
    got = store.get("006360", "94082")
    assert got and got["report_id"] == "94082"
    assert store.get("006360", "nope") is None


def test_list_empty_for_unknown(store):
    assert store.list_reports("000000") == []


def test_scope_isolation(store):
    # 다른 종목(scope)은 서로 안 보인다(공동 DB지만 종목별 분리).
    store.upsert("006360", _entry("1"))
    store.upsert("000660", _entry("2"))
    assert [r["report_id"] for r in store.list_reports("006360")] == ["1"]
    assert [r["report_id"] for r in store.list_reports("000660")] == ["2"]
