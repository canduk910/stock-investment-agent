"""시황(market outlook) 요약 라우터 — 시장 국면 페이지에 표시할 증권사 시황 리포트 요약.

POST /api/macro/market-outlook/fetch : 네이버 최신 시황 수집→요약→저장(병렬·graceful).
GET  /api/macro/market-outlook       : 저장된 시황 요약 리스트(최신순).
조회/색인 전용(매매 없음). 요약은 '시황 리포트 인용'(에이전트 시장 판정 아님)·면책. 정적 문서라 .cache 영속.
"""
from __future__ import annotations

from fastapi import APIRouter

from api._helpers import graceful_counts
from api._sse import sse_response
from chat import market_outlook_combined, market_outlook_service
from chat.market_outlook_store import default_store

router = APIRouter()


@router.post("/api/macro/market-outlook/fetch")
def fetch_market_outlook(limit: int = 15) -> dict:
    """네이버 최신 시황 수집→요약→저장. 항상 200 + 카운트({fetched,new,skipped,failed})."""
    limit = max(1, min(limit, 30))  # 예의 크롤링 상한
    return graceful_counts(
        lambda: market_outlook_service.fetch_and_summarize(limit=limit),
        {"fetched": 0, "new": 0, "skipped": 0, "failed": 0},
    )


@router.post("/api/macro/market-outlook/fetch/stream")
def fetch_market_outlook_stream(limit: int = 15):
    """네이버 최신 시황 수집→요약 **SSE 진행 스트림**. non-stream fetch 는 폴백 유지."""
    limit = max(1, min(limit, 30))
    return sse_response(market_outlook_service.iter_fetch_and_summarize(limit=limit))


@router.get("/api/macro/market-outlook")
def market_outlook_summaries() -> dict:
    """저장된 시황 요약 리스트(최신순). 없으면 reports=[]."""
    return {"reports": default_store().list_reports()}


@router.post("/api/macro/market-outlook/summary")
def market_outlook_combined_summary() -> dict:
    """최근 **5개** 시황 리포트를 종합해 **10줄 '금일의 요약'** 생성(온디맨드).

    저장된 per-report 요약만으로 종합·중복제거(PDF 재다운로드 없음, 0 네이버). 리포트 0개·검증
    실패는 graceful(항상 200 + validation_failed). 종합은 '여러 시황 리포트 인용'(시장 판정 아님)·면책.
    """
    return graceful_counts(
        market_outlook_combined.summarize_recent_outlooks,
        {"summary": None, "validation_failed": True, "report_count": 0},
    )
