"""리포트 히스토리 저장소 테스트 — plan §"chat/report_store.py".

watchlist/store.py 와 동일 JSON-파일 패턴(원자적 write + threading.Lock). 다만 여기는
(ticker, created_at) 키의 append-only 히스토리다(과거 평가 비교 데모). 검증하는 계약:
- append → list_history 로 되읽기(created_at·regime_at_creation·report_json 보존).
- 같은 ticker 여러 평가 누적, created_at 내림차순(최신 우선) 반환.
- ticker 간 격리, 재오픈 지속성(tmp_path), 빈 히스토리.
경계(파일)만 실제로, 그 안쪽 append/정렬 로직은 실제 코드로 통과시킨다.
"""
from __future__ import annotations

from chat.report_store import JsonFileReportStore


def _report(opinion="중립"):
    return {
        "종합의견": opinion,
        "요약": "요약",
        "투자포인트": ["a"],
        "리스크요인": ["b"],
        "국면정합성": "정합성",
        "면책고지": "참고용",
    }


def test_append_then_list_roundtrips(tmp_path):
    store = JsonFileReportStore(tmp_path / "reports.json")
    entry = store.append("005930", _report("긍정적"), regime_at_creation="과열")

    history = store.list_history("005930")
    assert len(history) == 1
    assert history[0]["report_json"]["종합의견"] == "긍정적"
    assert history[0]["regime_at_creation"] == "과열"
    assert history[0]["created_at"]  # ISO8601 시각 존재
    assert entry["created_at"] == history[0]["created_at"]


def test_history_isolated_by_ticker(tmp_path):
    store = JsonFileReportStore(tmp_path / "reports.json")
    store.append("005930", _report(), regime_at_creation="과열")
    store.append("000660", _report(), regime_at_creation="수축")

    assert len(store.list_history("005930")) == 1
    assert len(store.list_history("000660")) == 1
    assert store.list_history("999999") == []


def test_multiple_evaluations_accumulate_newest_first(tmp_path):
    store = JsonFileReportStore(tmp_path / "reports.json")
    store.append("005930", _report("신중"), regime_at_creation="과열", created_at="2026-01-01T00:00:00+00:00")
    store.append("005930", _report("긍정적"), regime_at_creation="수축", created_at="2026-07-01T00:00:00+00:00")

    history = store.list_history("005930")
    assert len(history) == 2
    # created_at 내림차순(최신 우선) — 과거 평가 비교 데모.
    assert history[0]["created_at"] > history[1]["created_at"]
    assert history[0]["report_json"]["종합의견"] == "긍정적"


def test_persistence_across_reopen(tmp_path):
    path = tmp_path / "reports.json"
    JsonFileReportStore(path).append("005930", _report(), regime_at_creation="과열")

    # 새 인스턴스로 재오픈 → 디스크에서 되읽기.
    reopened = JsonFileReportStore(path)
    assert len(reopened.list_history("005930")) == 1


def test_empty_history_for_unknown_ticker(tmp_path):
    store = JsonFileReportStore(tmp_path / "reports.json")
    assert store.list_history("005930") == []


def test_created_at_auto_generated_when_absent(tmp_path):
    # created_at 미전달 시 자동 생성(현재 UTC ISO8601).
    store = JsonFileReportStore(tmp_path / "reports.json")
    entry = store.append("005930", _report(), regime_at_creation="과열")
    assert entry["created_at"]
    assert "T" in entry["created_at"]  # ISO8601 날짜·시각 구분자
