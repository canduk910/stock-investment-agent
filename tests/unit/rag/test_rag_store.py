"""RAG 인덱스 테스트 — numpy 코사인 검색 + 영속화 + reindex/search(임베딩 mock)."""
from __future__ import annotations

import numpy as np

from rag import store
from rag.store import ReportStore


def test_search_ranks_by_cosine():
    chunks = [
        {"text": "삼성전자 목표가 9만원", "source": "a.pdf"},
        {"text": "금리 인상 전망", "source": "b.pdf"},
        {"text": "반도체 업황 개선", "source": "a.pdf"},
    ]
    emb = np.array([[1, 0, 0], [0, 1, 0], [0.9, 0.1, 0]], dtype="float32")
    s = ReportStore(chunks, emb)
    hits = s.search(np.array([1, 0, 0], dtype="float32"), top_k=2)
    assert len(hits) == 2
    # 쿼리 [1,0,0] 과 가장 가까운 건 0번(=1,0,0), 다음 2번(0.9,0.1,0).
    assert hits[0]["source"] == "a.pdf" and "목표가" in hits[0]["text"]
    assert hits[1]["text"] == "반도체 업황 개선"
    assert hits[0]["score"] >= hits[1]["score"]


def test_search_empty_store_is_empty():
    assert ReportStore().search(np.array([1.0, 0.0], dtype="float32")) == []
    # 쿼리 벡터가 비어도 안전.
    s = ReportStore([{"text": "x", "source": "a"}], np.array([[1.0]], dtype="float32"))
    assert s.search(np.zeros((0,), dtype="float32")) == []


def test_save_load_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_CHUNKS_PATH", str(tmp_path / "c.json"))
    monkeypatch.setattr(store, "_EMB_PATH", str(tmp_path / "e.npy"))
    chunks = [{"text": "본문", "source": "a.pdf"}]
    emb = np.array([[0.1, 0.2, 0.3]], dtype="float32")
    ReportStore(chunks, emb).save()
    loaded = ReportStore.load()
    assert loaded.chunks == chunks
    assert np.allclose(loaded.embeddings, emb)


def test_reindex_and_search_reports(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_CHUNKS_PATH", str(tmp_path / "c.json"))
    monkeypatch.setattr(store, "_EMB_PATH", str(tmp_path / "e.npy"))
    monkeypatch.setattr(store, "_store", None)  # 싱글톤 초기화
    # ingest·embed mock — 라이브 미호출.
    monkeypatch.setattr(
        store.ingest, "ingest_folder",
        lambda folder: [
            {"text": "삼성 목표가 9만", "source": "r.pdf"},
            {"text": "SK 목표가 20만", "source": "r.pdf"},
        ],
    )
    monkeypatch.setattr(
        store.embed, "embed_texts",
        lambda texts, client=None: np.array([[1, 0], [0, 1]], dtype="float32"),
    )
    summary = store.reindex(folder="reports")
    assert summary == {"reports": 1, "chunks": 2, "sources": ["r.pdf"]}

    # 검색: 쿼리 임베딩 mock → 0번(삼성) 쪽으로.
    monkeypatch.setattr(store.embed, "embed_query", lambda q, client=None: np.array([1, 0], dtype="float32"))
    hits = store.search_reports("삼성 목표가", top_k=1)
    assert hits and hits[0]["source"] == "r.pdf" and "삼성" in hits[0]["text"]


def test_reindex_empty_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_CHUNKS_PATH", str(tmp_path / "c.json"))
    monkeypatch.setattr(store, "_EMB_PATH", str(tmp_path / "e.npy"))
    monkeypatch.setattr(store, "_store", None)
    monkeypatch.setattr(store.ingest, "ingest_folder", lambda folder: [])
    assert store.reindex() == {"reports": 0, "chunks": 0, "sources": []}
    assert store.search_reports("무엇이든") == []  # 인덱스 없음 → 빈
