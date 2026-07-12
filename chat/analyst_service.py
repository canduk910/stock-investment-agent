"""네이버 애널리스트 리포트 수집→요약→저장 오케스트레이션.

fetch_company_reports(목록·메타) → 종목별로 병렬(ThreadPool):
  이미 요약한 nid skip(idempotent) → download_pdf → extract_text → summarize_report → store.upsert.
항상 dict 카운트 반환(크래시 없음, 개별 실패는 failed 로 집계). store.upsert 는 AtomicJsonFile 락으로 스레드 안전.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

_MAX_WORKERS = 4  # 네이버 예의 크롤링 + OpenAI 동시 요약 상한


def _process_one(meta: dict, *, store, client) -> str:
    """리포트 1건 처리 → 결과 라벨('new'|'skipped'|'failed'). 예외는 'failed'로 흡수."""
    from chat import analyst_report
    from collectors import naver_research
    from rag.ingest import extract_text

    ticker = meta.get("stock_code")
    rid = meta.get("nid")
    if not ticker or not rid:
        return "failed"
    if store.has(ticker, rid):
        return "skipped"
    try:
        pdf = naver_research.download_pdf(meta.get("pdf_url", ""))
        if not pdf:
            return "failed"
        text = extract_text(pdf)
        result = analyst_report.summarize_report(text, meta, client=client)
        if result.get("validation_failed") or not result.get("summary"):
            return "failed"
        added = store.upsert(ticker, {
            "report_id": rid,
            "broker": meta.get("broker", ""),
            "stock_name": meta.get("stock_name", ""),
            "title": meta.get("title", ""),
            "date": meta.get("date", ""),
            "pdf_url": meta.get("pdf_url", ""),
            "summary": result["summary"],
        })
        return "new" if added else "skipped"
    except Exception:
        return "failed"  # 개별 리포트 실패는 전체를 막지 않음


def _summarize_metas(metas: list[dict], *, store, client) -> dict:
    """메타 리스트 → 병렬 처리 카운트({fetched,new,skipped,failed})."""
    counts = {"new": 0, "skipped": 0, "failed": 0}
    if metas:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
            for label in ex.map(lambda m: _process_one(m, store=store, client=client), metas):
                counts[label] += 1
    return {"fetched": len(metas), **counts}


def fetch_and_summarize(limit: int = 20, *, client=None, store=None) -> dict:
    """네이버 최신 리포트(전체 피드) 수집→요약→저장. {fetched, new, skipped, failed} 반환(항상)."""
    from chat.analyst_store import default_store
    from collectors import naver_research

    store = store or default_store()
    return _summarize_metas(naver_research.fetch_company_reports(limit=limit), store=store, client=client)


def fetch_and_summarize_for_ticker(ticker: str, limit: int = 10, *, client=None, store=None) -> dict:
    """**특정 종목**의 네이버 리포트(itemCode 필터) 수집→요약→저장. 종목 상세의 '이 종목 가져오기'용."""
    from chat.analyst_store import default_store
    from collectors import naver_research

    store = store or default_store()
    return _summarize_metas(
        naver_research.fetch_stock_reports(ticker, limit=limit), store=store, client=client
    )


def iter_fetch_and_summarize_for_ticker(ticker: str, limit: int = 10, *, client=None, store=None):
    """**특정 종목** 수집→요약을 진행 이벤트로 스트리밍(SSE용). stage:list → found → progress → done."""
    from chat.analyst_store import default_store
    from chat.report_progress import iter_process_metas
    from collectors import naver_research

    store = store or default_store()
    yield {"type": "stage", "stage": "list"}
    metas = naver_research.fetch_stock_reports(ticker, limit=limit)
    yield from iter_process_metas(
        metas,
        lambda m: _process_one(m, store=store, client=client),
        id_of=lambda m: m.get("nid"),
    )
