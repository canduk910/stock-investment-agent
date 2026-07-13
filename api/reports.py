"""증권사 리포트 PDF RAG 라우터 + 네이버 애널리스트 리포트 수집·종목별 조회.

POST /api/reports/reindex : reports 폴더 재스캔 → 청킹 → 임베딩 → 인덱스 재구축·영속화.
GET  /api/reports/status  : 현재 인덱스 요약(리포트 수·청크 수·파일명).
POST /api/reports/fetch   : 네이버 최신 리포트 수집→다운로드→요약→store(병렬, graceful).
GET  /api/detail/{ticker}/analyst-reports : 그 종목의 저장된 애널리스트 요약 리스트.
색인/조회 전용(매매 없음). 요약은 '리포트 내용 인용'(에이전트 판정 아님)·면책. 인덱스/요약은 정적 문서라 .cache 영속.
"""
from __future__ import annotations

from fastapi import APIRouter

from api._sse import sse_response
from api.deps import assert_valid_ticker
from chat import analyst_combined, analyst_service
from chat.analyst_store import default_store
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


@router.post("/api/reports/fetch")
def fetch_naver_reports(limit: int = 20) -> dict:
    """네이버 최신 리포트 수집→요약→저장. 항상 200 + 카운트({fetched,new,skipped,failed})."""
    limit = max(1, min(limit, 50))  # 예의 크롤링 상한
    try:
        return analyst_service.fetch_and_summarize(limit=limit)
    except Exception as e:  # 수집/요약 실패 — 크래시 대신 안내
        return {"error": str(e)[:200], "fetched": 0, "new": 0, "skipped": 0, "failed": 0}


@router.post("/api/detail/{ticker}/analyst-reports/fetch")
def fetch_stock_analyst_reports(ticker: str, limit: int = 10) -> dict:
    """**이 종목**의 네이버 리포트(itemCode 필터) 수집→요약→저장. 항상 200 + 카운트.

    전체 최신 피드가 아니라 그 종목의 리포트만 가져온다(종목 상세 '이 종목 가져오기').
    """
    assert_valid_ticker(ticker)  # 불량 코드 400(공용 SSOT)
    limit = max(1, min(limit, 30))  # 예의 크롤링 상한
    try:
        return analyst_service.fetch_and_summarize_for_ticker(ticker, limit=limit)
    except Exception as e:  # 수집/요약 실패 — 크래시 대신 안내
        return {"error": str(e)[:200], "fetched": 0, "new": 0, "skipped": 0, "failed": 0}


@router.post("/api/detail/{ticker}/analyst-reports/fetch/stream")
def fetch_stock_analyst_reports_stream(ticker: str, limit: int = 10):
    """이 종목 리포트 수집→요약 **SSE 진행 스트림**(목록→각 리포트→완료). non-stream fetch 는 폴백 유지."""
    assert_valid_ticker(ticker)  # 불량 코드 400(스트림 전 차단)
    limit = max(1, min(limit, 30))
    return sse_response(analyst_service.iter_fetch_and_summarize_for_ticker(ticker, limit=limit))


@router.get("/api/detail/{ticker}/analyst-reports")
def analyst_reports(ticker: str) -> dict:
    """종목별 저장된 애널리스트 리포트 요약 리스트(최신순). 없으면 reports=[]."""
    assert_valid_ticker(ticker)  # 불량 코드 400(공용 SSOT)
    return {"ticker": ticker, "reports": default_store().list_reports(ticker)}


@router.post("/api/detail/{ticker}/analyst-reports/summary")
def analyst_reports_summary(ticker: str) -> dict:
    """이 종목 **최근 3개** 애널리스트 리포트를 종합해 10줄로 요약(항목5, 온디맨드).

    저장된 per-report 요약만으로 종합(PDF 재다운로드 없음, 0 네이버/KIS). 리포트 0개·검증
    실패는 graceful(항상 200 + validation_failed). 종합은 '여러 리포트 인용'(판정 아님)·면책.
    """
    assert_valid_ticker(ticker)  # 불량 코드 400(공용 SSOT)
    try:
        result = analyst_combined.summarize_recent_reports(ticker)
    except Exception as e:  # LLM/조회 실패 — 크래시 대신 안내
        return {
            "ticker": ticker, "summary": None, "validation_failed": True,
            "report_count": 0, "error": str(e)[:200],
        }
    return {"ticker": ticker, **result}
