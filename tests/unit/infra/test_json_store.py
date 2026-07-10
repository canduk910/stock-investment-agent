"""AtomicJsonFile — durable store 공용 원자적 JSON I/O(IMP-13).

watchlist/store·report_store 가 has-a 로 공유하는 디스크 계층. 원자성·손상 방어를 여기서 고정.
"""
from __future__ import annotations

from infra.json_store import AtomicJsonFile


def test_write_then_read_roundtrip(tmp_path):
    f = AtomicJsonFile(tmp_path / "sub" / "x.json")  # 없는 하위 디렉토리도 생성
    f.write({"a": {"b": 1}, "한글": "값"})
    assert f.read() == {"a": {"b": 1}, "한글": "값"}


def test_missing_file_reads_empty(tmp_path):
    assert AtomicJsonFile(tmp_path / "nope.json").read() == {}


def test_corrupt_or_non_dict_reads_empty(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert AtomicJsonFile(p).read() == {}
    p.write_text("[1, 2, 3]", encoding="utf-8")  # 비-dict → 빈 dict
    assert AtomicJsonFile(p).read() == {}


def test_write_leaves_no_temp_and_keeps_hangul(tmp_path):
    p = tmp_path / "x.json"
    f = AtomicJsonFile(p)
    f.write({"한": "글"})
    # os.replace 로 교체 → temp 파일이 남지 않는다.
    assert [q.name for q in tmp_path.iterdir() if ".tmp." in q.name] == []
    # ensure_ascii=False → 한글이 이스케이프 없이 저장.
    assert "한" in p.read_text(encoding="utf-8")


def test_lock_context_guards_read_modify_write(tmp_path):
    f = AtomicJsonFile(tmp_path / "x.json")
    with f.lock():
        raw = f.read()
        raw["a"] = 1
        f.write(raw)
    assert f.read() == {"a": 1}
