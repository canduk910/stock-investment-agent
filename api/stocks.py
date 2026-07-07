"""종목 검색(자동완성) 라우트 — GET /api/stocks/search?q=&limit=.

KIS 는 종목명 검색 API 를 주지 않으므로, 공개 마스터 파일을 파싱한 목록(collectors.stock_master)을
메모리에 한 번 로드해 이름/코드로 검색한다. 시세가 아니라 정적 참조라 매 요청 조회하지 않는다.
"""
from __future__ import annotations

from fastapi import APIRouter

from collectors.stock_master import load_stock_master, search_stocks

router = APIRouter()

_MASTER: list[dict] | None = None


def _get_master() -> list[dict]:
    """마스터를 프로세스 메모리에 1회 로드(캐시 파일 경유). 테스트는 이 함수를 monkeypatch."""
    global _MASTER
    if _MASTER is None:
        _MASTER = load_stock_master()
    return _MASTER


@router.get("/api/stocks/search")
def stocks_search(q: str = "", limit: int = 8) -> dict:
    """종목명/코드 자동완성 → {results: [{ticker, name, market}]}.

    마스터 로드 실패해도 죽지 않는다(빈 결과 + error 표기 — 프론트는 직접 코드 입력 폴백).
    """
    capped = max(1, min(limit, 30))
    try:
        master = _get_master()
    except Exception:
        return {"results": [], "error": "종목 마스터 로드 실패 — 종목코드 직접 입력"}
    return {"results": search_stocks(master, q, capped)}
