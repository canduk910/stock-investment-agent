"""리포트 배치 처리 진행 이벤트 제너레이터 — analyst·market_outlook 공용.

목록(metas) → 각 리포트를 ThreadPool 로 처리하며 **완료 순**으로 progress 이벤트를 yield 한다.
`process_one(meta) -> 'new'|'skipped'|'failed'`(예외는 'failed' 로 흡수), `id_of(meta) -> 식별자(nid)`.

이벤트 계약(SSE SSOT, 프론트 `lib/sse` 와 공유):
  {"type":"found","reports":[{id,broker,title,stock_name?}]}   # N건 발견(체크리스트 원천)
  {"type":"progress","id","result","done","total"}             # 각 리포트 완료 시
  {"type":"done","fetched","new","skipped","failed"}           # 종료 카운트
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Iterable, Iterator

_MAX_WORKERS = 4  # 네이버 예의 크롤링 + OpenAI 동시 요약 상한(서비스 _MAX_WORKERS 와 동일)


def run_batch(metas: Iterable[dict], process_one: Callable[[dict], str]) -> dict:
    """metas → 병렬 처리(ThreadPool.map) → {fetched,new,skipped,failed}. non-stream 배치 SSOT.

    analyst_service·market_outlook_service 의 비스트림 수집 루프 단일 출처(스트림은
    iter_process_metas). `process_one(meta)->'new'|'skipped'|'failed'`(예외는 콜백이 흡수).
    """
    metas = list(metas)
    counts = {"new": 0, "skipped": 0, "failed": 0}
    if metas:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
            for label in ex.map(process_one, metas):
                counts[label] += 1
    return {"fetched": len(metas), **counts}


def _report_meta(meta: dict, id_of: Callable[[dict], str]) -> dict:
    out = {"id": id_of(meta), "broker": meta.get("broker", ""), "title": meta.get("title", "")}
    if meta.get("stock_name"):  # 종목 리포트만(시황은 없음)
        out["stock_name"] = meta["stock_name"]
    return out


def iter_process_metas(
    metas: Iterable[dict],
    process_one: Callable[[dict], str],
    *,
    id_of: Callable[[dict], str],
) -> Iterator[dict]:
    """found → (병렬 처리, 완료마다) progress → done 이벤트를 순서대로 yield."""
    metas = list(metas)
    yield {"type": "found", "reports": [_report_meta(m, id_of) for m in metas]}

    counts = {"new": 0, "skipped": 0, "failed": 0}
    total = len(metas)
    done = 0
    if metas:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
            futures = {ex.submit(process_one, m): m for m in metas}
            for fut in as_completed(futures):
                m = futures[fut]
                try:
                    label = fut.result()
                except Exception:
                    label = "failed"  # 개별 실패는 전체를 막지 않는다
                counts[label] = counts.get(label, 0) + 1
                done += 1
                yield {
                    "type": "progress",
                    "id": id_of(m),
                    "result": label,
                    "done": done,
                    "total": total,
                }
    yield {"type": "done", "fetched": total, **counts}
