"""네이버 시황(market outlook) 수집→요약→저장 오케스트레이션(analyst_service 패턴).

fetch_reports("market", ...) → 병렬(ThreadPool): 이미 요약한 nid skip(idempotent) → download_pdf
→ extract_text → summarize_market_outlook → store.upsert. 항상 dict 카운트 반환(크래시 없음).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

_MAX_WORKERS = 4  # 네이버 예의 크롤링 + OpenAI 동시 요약 상한


def _process_one(meta: dict, *, store, client) -> str:
    """시황 리포트 1건 처리 → 결과 라벨('new'|'skipped'|'failed'). 예외는 'failed'로 흡수."""
    from chat import market_outlook
    from collectors import naver_research
    from rag.ingest import extract_text

    rid = meta.get("nid")
    if not rid:
        return "failed"
    if store.has(rid):
        return "skipped"
    try:
        pdf = naver_research.download_pdf(meta.get("pdf_url", ""), dest_dir="reports/naver_market")
        if not pdf:
            return "failed"
        text = extract_text(pdf)
        result = market_outlook.summarize_market_outlook(text, meta, client=client)
        if result.get("validation_failed") or not result.get("summary"):
            return "failed"
        added = store.upsert({
            "report_id": rid,
            "broker": meta.get("broker", ""),
            "title": meta.get("title", ""),
            "date": meta.get("date", ""),
            "pdf_url": meta.get("pdf_url", ""),
            "summary": result["summary"],
        })
        return "new" if added else "skipped"
    except Exception:
        return "failed"  # 개별 리포트 실패는 전체를 막지 않음


def fetch_and_summarize(limit: int = 15, *, client=None, store=None) -> dict:
    """네이버 최신 시황 수집→요약→저장. {fetched, new, skipped, failed} 반환(항상)."""
    from chat.market_outlook_store import default_store
    from collectors import naver_research

    store = store or default_store()
    metas = naver_research.fetch_reports("market", limit=limit)
    counts = {"new": 0, "skipped": 0, "failed": 0}
    if metas:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
            for label in ex.map(lambda m: _process_one(m, store=store, client=client), metas):
                counts[label] += 1
    return {"fetched": len(metas), **counts}


def iter_fetch_and_summarize(limit: int = 15, *, client=None, store=None):
    """네이버 최신 시황 수집→요약을 진행 이벤트로 스트리밍(SSE용). stage:list → found → progress → done."""
    from chat.market_outlook_store import default_store
    from chat.report_progress import iter_process_metas
    from collectors import naver_research

    store = store or default_store()
    yield {"type": "stage", "stage": "list"}
    metas = naver_research.fetch_reports("market", limit=limit)
    yield from iter_process_metas(
        metas,
        lambda m: _process_one(m, store=store, client=client),
        id_of=lambda m: m.get("nid"),
    )
