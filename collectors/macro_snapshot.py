"""매크로 지표 스냅샷 집계 — plan §5.1 (번들 패턴).

대시보드 하나가 지표 6종을 각각 순차 조회하면 N+1 로 느려진다. 여기서 KIS/FRED/
CNN 을 ThreadPool 로 병렬 수집해 한 번에 반환하고, 한 소스가 실패해도 전체를 죽이지
않고 partial_failure 에 기록한다(성공분은 채우고 실패분은 None).

반환: {"indicators": {key: IndicatorPoint | None}, "partial_failure": [key, ...]}
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from collectors import fear_greed, fred, vix

# 대시보드가 표시하는 지표(키 → 수집 호출). fred_key 를 클로저로 받는다.
_FETCH_TIMEOUT = 15


def _fetchers(fred_key: str) -> dict[str, Callable[[], Any]]:
    return {
        "t10y2y": lambda: fred.fetch_t10y2y(fred_key),
        "hy_spread": lambda: fred.fetch_hy_spread(fred_key),
        "dollar_index": lambda: fred.fetch_dollar_index(fred_key),
        "gdp": lambda: fred.fetch_gdp(fred_key),
        "vix": lambda: vix.fetch_vix(fred_api_key=fred_key),
        "fear_greed": lambda: fear_greed.fetch_fear_greed(),
    }


def collect_macro_indicators(fred_key: str) -> dict:
    """6종 지표를 병렬 수집. 실패/None 은 partial_failure 에 기록."""
    fetchers = _fetchers(fred_key)
    indicators: dict[str, Any] = {}
    failures: list[str] = []

    with ThreadPoolExecutor(max_workers=len(fetchers)) as ex:
        futures = {key: ex.submit(fn) for key, fn in fetchers.items()}
        for key, future in futures.items():
            try:
                point = future.result(timeout=_FETCH_TIMEOUT)
            except Exception:
                point = None
            indicators[key] = point
            if point is None:  # 예외 또는 graceful None(공포탐욕 CNN 실패 등)
                failures.append(key)

    return {"indicators": indicators, "partial_failure": failures}
