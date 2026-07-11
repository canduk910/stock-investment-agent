"""증권사 리포트 PDF RAG 라우터 — 폴더 인덱스 재구축·상태(챗 search_report 의 관리 API).

POST /api/reports/reindex : reports 폴더 재스캔 → 청킹 → 임베딩 → 인덱스 재구축·영속화.
GET  /api/reports/status  : 현재 인덱스 요약(리포트 수·청크 수·파일명).
색인/조회 전용(매매 없음). 임베딩은 요청 시 라이브 호출, 인덱스는 정적 리포트라 .cache 영속.
"""
from __future__ import annotations

from fastapi import APIRouter

from rag import store

router = APIRouter()


@router.post("/api/reports/reindex")
def reindex_reports() -> dict:
    """reports 폴더 PDF 재인덱스. 임베딩/파싱 실패는 graceful(항상 200 + error 필드)."""
    try:
        return store.reindex()
    except Exception as e:  # OpenAI/파싱 실패 — 크래시 대신 안내
        return {"error": str(e)[:200], "reports": 0, "chunks": 0, "sources": []}


@router.get("/api/reports/status")
def reports_status() -> dict:
    return store.status()
