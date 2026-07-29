"""리포트 RAG 인덱스 — numpy 임베딩 저장 + 코사인 top-k 검색 + .cache 영속화.

FAISS 대신 numpy 브루트포스(리포트 소수 규모라 충분·의존성 절감). 리포트는 정적 문서 →
인덱스 캐시 허용(현재가 아님, 원칙1 무관). reindex 로 폴더 재스캔, search_reports 로 조회.
싱글톤(lazy)으로 챗 쿼리마다 디스크 재로드를 피한다.
"""
from __future__ import annotations

import json
import os

import numpy as np

from rag import embed, ingest

# 리포트 PDF 투입 폴더(env 재정의 가능). 인덱스 영속화 경로(.cache — 정적 리포트).
REPORTS_DIR = os.environ.get("REPORTS_DIR", "reports")
_CACHE_DIR = ".cache"
_CHUNKS_PATH = os.path.join(_CACHE_DIR, "report_rag_chunks.json")
_EMB_PATH = os.path.join(_CACHE_DIR, "report_rag_emb.npy")


def _normalize_rows(m: np.ndarray) -> np.ndarray:
    """행 벡터를 L2 정규화 → 정규화 벡터 내적 = 코사인 유사도.

    영벡터는 노름 0 이라 나눗셈이 NaN 이 되므로 노름 0 을 1 로 치환(0/1=0, 안전).
    """
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0  # 0 나눗셈 방지(영벡터 → 0 벡터 유지)
    return m / norms


class ReportStore:
    """청크([{text, source}]) + 임베딩 행렬((n, dim))을 들고 코사인 검색한다."""

    def __init__(self, chunks=None, embeddings=None):
        self.chunks = chunks or []
        self.embeddings = (
            embeddings if embeddings is not None else np.zeros((0, 0), dtype="float32")
        )

    def search(self, query_emb: np.ndarray, top_k: int = 3) -> list[dict]:
        """쿼리 임베딩 → 코사인 top-k 청크([{...chunk, score}]). 인덱스·쿼리 비면 빈 리스트."""
        # 인덱스가 비었거나 쿼리 임베딩이 없으면 검색 불가 → 조용히 빈 결과(호출측 graceful).
        if (
            not self.chunks
            or self.embeddings.shape[0] == 0
            or query_emb is None
            or query_emb.shape[0] == 0
        ):
            return []
        docs = _normalize_rows(self.embeddings)  # 문서 벡터 정규화
        q = query_emb / (float(np.linalg.norm(query_emb)) or 1.0)  # 쿼리 정규화(노름 0→1 방어)
        scores = docs @ q  # 정규화 내적 = 코사인 유사도 벡터(n,)
        k = min(top_k, len(self.chunks))  # 청크 수보다 큰 top_k 방어
        idx = np.argsort(-scores)[:k]  # 음수 정렬로 내림차순 → 상위 k 인덱스
        return [{**self.chunks[i], "score": float(scores[i])} for i in idx]

    def save(self) -> None:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        with open(_CHUNKS_PATH, "w", encoding="utf-8") as f:
            json.dump(self.chunks, f, ensure_ascii=False)
        np.save(_EMB_PATH, self.embeddings)

    @classmethod
    def load(cls) -> "ReportStore":
        """.cache 에서 청크+임베딩을 복원. 파일 부재·손상은 빈 store(reindex 전까지 검색 0건)."""
        # 두 파일(청크 JSON + 임베딩 npy)이 모두 있어야 유효한 인덱스.
        if not (os.path.exists(_CHUNKS_PATH) and os.path.exists(_EMB_PATH)):
            return cls()
        try:
            with open(_CHUNKS_PATH, encoding="utf-8") as f:
                chunks = json.load(f)
            return cls(chunks, np.load(_EMB_PATH))
        except Exception:
            # 손상된 캐시가 앱을 죽이면 안 됨 → 빈 store 로 안전 강등(reindex 로 재구축).
            return cls()


# 모듈 싱글톤(lazy) — reindex 가 교체한다.
_store: ReportStore | None = None


def _get_store() -> ReportStore:
    global _store
    if _store is None:
        _store = ReportStore.load()
    return _store


def reindex(folder: str | None = None, client=None) -> dict:
    """폴더 재스캔 → 청크 → 임베딩 → 인덱스 재구축·영속화. 요약 dict 반환.

    싱글톤 `_store` 를 새 인덱스로 통째 교체한다(부분 갱신 아님 — 폴더가 곧 진실).
    청크 0개면 빈 인덱스로 리셋(이전 인덱스 잔존 방지).
    """
    global _store
    folder = folder or REPORTS_DIR
    chunks = ingest.ingest_folder(folder)
    if not chunks:
        # 폴더가 비었으면 빈 인덱스로 저장 후 조기 반환(임베딩 API 호출 낭비 0).
        _store = ReportStore()
        _store.save()
        return {"reports": 0, "chunks": 0, "sources": []}
    # 청크 텍스트만 뽑아 배치 임베딩 → 청크와 임베딩 행이 1:1 대응(인덱스 정렬 계약).
    embeddings = embed.embed_texts([c["text"] for c in chunks], client=client)
    _store = ReportStore(chunks, embeddings)
    _store.save()
    sources = sorted({c["source"] for c in chunks})  # 원본 파일명 집합(중복 제거)
    return {"reports": len(sources), "chunks": len(chunks), "sources": sources}


def status() -> dict:
    s = _get_store()
    sources = sorted({c["source"] for c in s.chunks})
    return {"reports": len(sources), "chunks": len(s.chunks), "sources": sources}


def search_reports(query: str, top_k: int = 3, client=None) -> list[dict]:
    """쿼리 → top-k 리포트 청크([{text, source, score}]). 인덱스 없으면 빈 리스트.

    챗 콘텐츠 툴 search_report 의 실체 — 사용자가 올린 PDF 인덱스에서 쿼리에 가까운 청크를 찾는다.
    인덱스가 비어 있으면 임베딩 API 호출조차 하지 않고 조기 반환(비용·지연 절감).
    """
    s = _get_store()
    if not s.chunks:
        return []
    q = embed.embed_query(query, client=client)  # 쿼리 임베딩(문서와 같은 임베딩 공간)
    return s.search(q, top_k=top_k)
