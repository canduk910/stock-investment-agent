"""병렬 조회 공용 헬퍼 — ThreadPool 로 {key: fn} 을 동시 실행, per-item graceful.

번들 섹션 병렬(api/detail)·스파크 병렬(watchlist/service)이 각자 갖던 동일 골격의 단일 출처.
각 job 은 독립 — 하나가 실패(예외/타임아웃)해도 전체를 죽이지 않고 그 key 만 None + failed 기록.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable


def fetch_parallel(
    jobs: dict[str, Callable[[], object]], *, max_workers: int, timeout: float
) -> tuple[dict, list]:
    """{key: fn} → ({key: result|None}, [failed_keys]). 예외/타임아웃은 그 key 만 None + failed.

    - 순서: jobs 삽입 순으로 결과·failed 를 수집(dict 순서 보존).
    - failed 를 partial_failure 로 쓸지, 무시하고 results 만 쓸지는 호출부가 결정(스파크는 무시).
    """
    results: dict = {}
    failed: list = []
    if not jobs:
        return results, failed
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {key: ex.submit(fn) for key, fn in jobs.items()}
        for key, fut in futures.items():
            try:
                results[key] = fut.result(timeout=timeout)
            except Exception:
                results[key] = None
                failed.append(key)
    return results, failed
