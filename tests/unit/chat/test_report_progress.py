"""리포트 배치 진행 이벤트 제너레이터 — found→progress×N→done 시퀀스·카운트·graceful."""
from __future__ import annotations

from chat.report_progress import iter_process_metas

_METAS = [
    {"nid": "1", "broker": "한화", "title": "t1", "stock_name": "GS건설"},
    {"nid": "2", "broker": "미래", "title": "t2", "stock_name": "GS건설"},
    {"nid": "3", "broker": "키움", "title": "t3", "stock_name": "GS건설"},
]


def _id(m):
    return m.get("nid")


def test_event_sequence_found_progress_done():
    labels = {"1": "new", "2": "skipped", "3": "failed"}
    events = list(iter_process_metas(_METAS, lambda m: labels[m["nid"]], id_of=_id))
    assert events[0]["type"] == "found"
    assert {r["id"] for r in events[0]["reports"]} == {"1", "2", "3"}
    assert events[0]["reports"][0]["broker"] == "한화" and events[0]["reports"][0]["title"] == "t1"

    progress = [e for e in events if e["type"] == "progress"]
    assert len(progress) == 3
    assert {p["id"] for p in progress} == {"1", "2", "3"}  # 완료 순(순서 무관)
    assert progress[-1]["done"] == 3 and all(p["total"] == 3 for p in progress)
    assert all(p["result"] in ("new", "skipped", "failed") for p in progress)

    done = events[-1]
    assert done["type"] == "done"
    assert done == {"type": "done", "fetched": 3, "new": 1, "skipped": 1, "failed": 1}


def test_process_exception_counts_failed():
    def _boom(m):
        raise RuntimeError("boom")

    events = list(iter_process_metas(_METAS, _boom, id_of=_id))
    done = events[-1]
    assert done["failed"] == 3 and done["new"] == 0  # 예외는 failed 로 흡수(전체 안 막음)


def test_empty_metas_found_zero_then_done():
    events = list(iter_process_metas([], lambda m: "new", id_of=_id))
    assert events[0] == {"type": "found", "reports": []}
    assert events[-1] == {"type": "done", "fetched": 0, "new": 0, "skipped": 0, "failed": 0}
    assert not [e for e in events if e["type"] == "progress"]


def test_found_omits_stock_name_when_absent():
    metas = [{"nid": "9", "broker": "KB", "title": "시황"}]  # 시황은 stock_name 없음
    events = list(iter_process_metas(metas, lambda m: "new", id_of=_id))
    assert "stock_name" not in events[0]["reports"][0]
