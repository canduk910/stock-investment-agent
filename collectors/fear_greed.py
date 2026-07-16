"""CNN 공포탐욕지수 수집기 — plan §3, T7.

fear-and-greed 파이썬 래퍼(CNN 비공식)를 사용한다. CNN 페이지 구조는 언제든
깨질 수 있으므로 graceful: 예외를 삼키지 않되(로그) None을 반환해 전체
파이프라인을 죽이지 않는다. 호출자가 None을 받아 partial_failure에 기록한다.
"""
from __future__ import annotations

import datetime as dt
import logging

import requests

from collectors.base import indicator_point

logger = logging.getLogger(__name__)

# CNN 공포탐욕 과거 그래프데이터(비공식) — 히스토리 조회용. 브라우저 UA 필요(없으면 418).
_CNN_GRAPHDATA_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


def _cnn_get():
    """외부 라이브러리 호출 경계 — 테스트가 이 지점만 대체(mock)한다.

    fear_and_greed는 import 시 requests_cache를 전역 설치해 다른 테스트의
    HTTP mock(responses)을 오염시킨다. 그래서 지연 import한다.
    """
    import fear_and_greed

    return fear_and_greed.get()


def _cnn_graphdata() -> dict:
    """CNN 공포탐욕 과거 그래프데이터 JSON 경계 — 테스트가 이 지점을 mock한다.

    비공식 엔드포인트라 브라우저 UA가 필요하다. requests 직접 호출(fear_and_greed
    라이브러리의 requests_cache 전역 설치 오염을 피한다).
    """
    resp = requests.get(_CNN_GRAPHDATA_URL, headers={"User-Agent": _UA}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_fear_greed() -> dict | None:
    """공포탐욕지수 → IndicatorPoint. 실패 시 None(예외 미전파)."""
    try:
        result = _cnn_get()
    except Exception as exc:  # noqa: BLE001 — 외부 스크래핑은 어떤 예외든 격리
        logger.warning("공포탐욕지수 수집 실패(CNN): %s", exc)
        return None

    return indicator_point(
        key="fear_greed",
        value=float(result.value),
        as_of=result.last_update.date(),
        source="CNN",
    )


def fetch_fear_greed_history(months: int = 12) -> list[dict] | None:
    """공포탐욕 월단위 히스토리 → [{date, value}](과거→현재, 최근 months개) 또는 None.

    CNN graphdata(비공식·best-effort)를 **월별 마지막 관측**으로 리샘플. 실패·구조 변화는
    graceful None(라우트가 available:false 로 처리). 히스토리는 확정 과거값이라 캐시 가능.
    """
    try:
        data = _cnn_graphdata()
        series = ((data or {}).get("fear_and_greed_historical") or {}).get("data") or []
    except Exception as exc:  # noqa: BLE001 — 외부 스크래핑은 어떤 예외든 격리
        logger.warning("공포탐욕 히스토리 수집 실패(CNN graphdata): %s", exc)
        return None

    # 월별 **최신 관측(max x)** 선택 — 소스 정렬 가정에 의존하지 않는다(순서 뒤섞여도 견고).
    by_month: dict[str, tuple[float, dict]] = {}
    for row in series:
        x, y = row.get("x"), row.get("y")
        if x is None or y is None:
            continue
        try:
            xf = float(x)
            d = dt.datetime.fromtimestamp(xf / 1000, tz=dt.timezone.utc).date()
        except (ValueError, OverflowError, OSError):
            continue
        month = d.replace(day=1).isoformat()  # YYYY-MM-01
        prev = by_month.get(month)
        if prev is None or xf > prev[0]:  # 그 달의 가장 나중 관측만 유지
            by_month[month] = (xf, {"date": month, "value": round(float(y), 1)})

    points = [by_month[m][1] for m in sorted(by_month)]  # date 오름차순
    return points[-months:] if points else None
