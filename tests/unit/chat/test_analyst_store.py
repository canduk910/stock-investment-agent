"""애널리스트 요약 store — roundtrip·idempotent(report_id)·정렬·cap(tmp 파일)."""
from __future__ import annotations

from chat.analyst_store import AnalystReportStore


def _entry(rid, date="26.07.10", broker="한화투자증권"):
    return {"report_id": rid, "broker": broker, "title": f"리포트{rid}",
            "date": date, "pdf_url": f"https://x/{rid}.pdf",
            "summary": {"증권사": broker, "종목": "GS건설"}}


def test_upsert_and_list(tmp_path):
    s = AnalystReportStore(tmp_path / "a.json")
    assert s.upsert("006360", _entry("94082")) is True
    reports = s.list_reports("006360")
    assert len(reports) == 1 and reports[0]["report_id"] == "94082"
    assert reports[0]["created_at"]  # 자동 타임스탬프


def test_upsert_idempotent_by_report_id(tmp_path):
    s = AnalystReportStore(tmp_path / "a.json")
    assert s.upsert("006360", _entry("94082")) is True
    assert s.upsert("006360", _entry("94082")) is False  # 같은 nid → skip
    assert len(s.list_reports("006360")) == 1


def test_has(tmp_path):
    s = AnalystReportStore(tmp_path / "a.json")
    s.upsert("006360", _entry("94082"))
    assert s.has("006360", "94082") is True
    assert s.has("006360", "99999") is False
    assert s.has("000660", "94082") is False  # 종목 분리


def test_list_sorted_by_date_desc(tmp_path):
    s = AnalystReportStore(tmp_path / "a.json")
    s.upsert("006360", _entry("1", date="26.07.08"))
    s.upsert("006360", _entry("2", date="26.07.10"))
    s.upsert("006360", _entry("3", date="26.07.09"))
    dates = [r["date"] for r in s.list_reports("006360")]
    assert dates == ["26.07.10", "26.07.09", "26.07.08"]


def test_get_single(tmp_path):
    s = AnalystReportStore(tmp_path / "a.json")
    s.upsert("006360", _entry("94082"))
    got = s.get("006360", "94082")
    assert got and got["report_id"] == "94082"
    assert s.get("006360", "nope") is None


def test_list_empty_for_unknown(tmp_path):
    s = AnalystReportStore(tmp_path / "a.json")
    assert s.list_reports("000000") == []
