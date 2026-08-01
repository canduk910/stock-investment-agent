"""리포트 히스토리 저장소 테스트 — plan §"chat/report_store.py".

watchlist/store.py 와 동일 JSON-파일 패턴(원자적 write + threading.Lock). 다만 여기는
(user_id, ticker, created_at) 키의 append-only 히스토리다(과거 평가 비교 데모·유저 스코프). 검증 계약:
- append → list_history 로 되읽기(created_at·regime_at_creation·report_json 보존).
- 같은 ticker 여러 평가 누적, created_at 내림차순(최신 우선) 반환.
- ticker 간 격리, **유저 간 격리(크로스유저 차단)**, 재오픈 지속성(tmp_path), 빈 히스토리.
경계(파일)만 실제로, 그 안쪽 append/정렬 로직은 실제 코드로 통과시킨다.
"""
from __future__ import annotations

from chat.report_store import JsonFileReportStore

_UID = "1"  # 테스트 기본 유저 id(유저 스코프 저장 키)


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
    entry = store.append("005930", _report("긍정적"), regime_at_creation="과열", user_id=_UID)

    history = store.list_history("005930", user_id=_UID)
    assert len(history) == 1
    assert history[0]["report_json"]["종합의견"] == "긍정적"
    assert history[0]["regime_at_creation"] == "과열"
    assert history[0]["created_at"]  # ISO8601 시각 존재
    assert entry["created_at"] == history[0]["created_at"]


def test_history_isolated_by_ticker(tmp_path):
    store = JsonFileReportStore(tmp_path / "reports.json")
    store.append("005930", _report(), regime_at_creation="과열", user_id=_UID)
    store.append("000660", _report(), regime_at_creation="수축", user_id=_UID)

    assert len(store.list_history("005930", user_id=_UID)) == 1
    assert len(store.list_history("000660", user_id=_UID)) == 1
    assert store.list_history("999999", user_id=_UID) == []


def test_history_isolated_by_user(tmp_path):
    # 보안(#5): 유저 A 가 생성한 리포트는 유저 B 의 list_history 에 안 나온다(크로스유저 차단).
    store = JsonFileReportStore(tmp_path / "reports.json")
    store.append("005930", _report("긍정적"), regime_at_creation="과열", user_id="A")

    assert len(store.list_history("005930", user_id="A")) == 1  # 소유자엔 보임
    assert store.list_history("005930", user_id="B") == []      # 타 유저엔 안 보임
    # 같은 ticker 를 B 가 따로 저장해도 A/B 는 서로 격리된다.
    store.append("005930", _report("신중"), regime_at_creation="수축", user_id="B")
    a_hist = store.list_history("005930", user_id="A")
    b_hist = store.list_history("005930", user_id="B")
    assert len(a_hist) == 1 and a_hist[0]["report_json"]["종합의견"] == "긍정적"
    assert len(b_hist) == 1 and b_hist[0]["report_json"]["종합의견"] == "신중"


def test_multiple_evaluations_accumulate_newest_first(tmp_path):
    store = JsonFileReportStore(tmp_path / "reports.json")
    store.append("005930", _report("신중"), regime_at_creation="과열", created_at="2026-01-01T00:00:00+00:00", user_id=_UID)
    store.append("005930", _report("긍정적"), regime_at_creation="수축", created_at="2026-07-01T00:00:00+00:00", user_id=_UID)

    history = store.list_history("005930", user_id=_UID)
    assert len(history) == 2
    # created_at 내림차순(최신 우선) — 과거 평가 비교 데모.
    assert history[0]["created_at"] > history[1]["created_at"]
    assert history[0]["report_json"]["종합의견"] == "긍정적"


def test_persistence_across_reopen(tmp_path):
    path = tmp_path / "reports.json"
    JsonFileReportStore(path).append("005930", _report(), regime_at_creation="과열", user_id=_UID)

    # 새 인스턴스로 재오픈 → 디스크에서 되읽기.
    reopened = JsonFileReportStore(path)
    assert len(reopened.list_history("005930", user_id=_UID)) == 1


def test_empty_history_for_unknown_ticker(tmp_path):
    store = JsonFileReportStore(tmp_path / "reports.json")
    assert store.list_history("005930", user_id=_UID) == []


def test_legacy_global_records_ignored_gracefully(tmp_path):
    # 구 전역 포맷({ticker: [...]})은 유저 버킷으로 안 잡혀 graceful 무시(마이그레이션·손실 허용).
    import json

    path = tmp_path / "reports.json"
    path.write_text(
        json.dumps({"005930": [{"created_at": "2026-01-01T00:00:00+00:00",
                                "regime_at_creation": "과열", "report_json": _report()}]}),
        encoding="utf-8",
    )
    store = JsonFileReportStore(path)
    assert store.list_history("005930", user_id=_UID) == []  # 구 전역 레코드는 안 잡힘(격리)


def test_created_at_auto_generated_when_absent(tmp_path):
    # created_at 미전달 시 자동 생성(현재 UTC ISO8601).
    store = JsonFileReportStore(tmp_path / "reports.json")
    entry = store.append("005930", _report(), regime_at_creation="과열", user_id=_UID)
    assert entry["created_at"]
    assert "T" in entry["created_at"]  # ISO8601 날짜·시각 구분자


def test_history_capped_at_limit(tmp_path):
    # ticker 당 상한(REPORT_HISTORY_CAP) 초과 시 오래된 평가부터 제거(무한 누적 방지, IMP-16).
    from chat.report_store import REPORT_HISTORY_CAP

    store = JsonFileReportStore(tmp_path / "reports.json")
    for i in range(REPORT_HISTORY_CAP + 5):
        store.append(
            "005930", {"종합의견": "중립"}, regime_at_creation="확장",
            created_at=f"2026-01-{i + 1:02d}T00:00:00+00:00", user_id=_UID,
        )
    hist = store.list_history("005930", user_id=_UID)
    assert len(hist) == REPORT_HISTORY_CAP  # 상한 유지
    assert all(h["created_at"] >= "2026-01-06T00:00:00+00:00" for h in hist)  # 오래된 5개 제거


def test_concurrent_appends_no_lost_history(tmp_path):
    # N개 스레드가 동시에 append 해도 유실 0(락으로 read-modify-write 보호, IMP-20).
    import threading

    store = JsonFileReportStore(tmp_path / "reports.json")
    n = 16
    barrier = threading.Barrier(n)

    def worker(i):
        barrier.wait()
        store.append(
            "005930", {"종합의견": "중립"}, regime_at_creation="확장",
            created_at=f"2026-01-{i + 1:02d}T00:00:00+00:00", user_id=_UID,
        )

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert len(store.list_history("005930", user_id=_UID)) == n  # 유실 0
