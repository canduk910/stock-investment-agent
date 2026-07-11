"""RAG 인입 테스트 — 표 보존 청킹 + pdfplumber 추출(mock) + 폴더 스캔."""
from __future__ import annotations

from rag import ingest
from rag.ingest import chunk_text, extract_text, ingest_folder


def test_chunk_text_splits_by_word_budget():
    text = "\n".join(["단어 " * 50 for _ in range(4)])  # 라인당 ~50단어 × 4
    chunks = chunk_text(text, max_tokens=60)
    assert len(chunks) >= 2  # 60단어 예산이면 여러 청크
    assert all(c.strip() for c in chunks)


def test_chunk_text_preserves_table():
    text = "머리말\n| 종목 | 목표가 |\n| 삼성 | 9만 |\n| SK | 20만 |\n\n다음 문단"
    chunks = chunk_text(text, max_tokens=5)
    table_chunks = [c for c in chunks if "|" in c]
    assert table_chunks
    # 표는 한 덩어리로 보존(행이 쪼개지지 않음).
    assert "삼성" in table_chunks[0] and "SK" in table_chunks[0]


def test_chunk_text_empty():
    assert chunk_text("") == []
    assert chunk_text(None) == []


class _FakePage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class _FakePdf:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_extract_text_concatenates_pages(monkeypatch):
    monkeypatch.setattr(
        ingest.pdfplumber, "open",
        lambda p: _FakePdf([_FakePage("1페이지"), _FakePage("2페이지"), _FakePage(None)]),
    )
    assert extract_text("x.pdf") == "1페이지\n2페이지"


def test_extract_text_graceful_on_error(monkeypatch):
    def _boom(p):
        raise Exception("corrupt pdf")

    monkeypatch.setattr(ingest.pdfplumber, "open", _boom)
    assert extract_text("bad.pdf") == ""  # 예외 대신 빈 문자열


def test_ingest_folder_tags_source_and_handles_missing(monkeypatch, tmp_path):
    # 빈/부재 폴더 → 빈 리스트.
    assert ingest_folder(str(tmp_path)) == []
    assert ingest_folder("/no/such/dir") == []

    # PDF 2개 → source 파일명 태깅.
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(ingest, "extract_text", lambda p: "본문 내용")
    out = ingest_folder(str(tmp_path))
    sources = {c["source"] for c in out}
    assert sources == {"a.pdf", "b.pdf"}
    assert all(c["text"] for c in out)
