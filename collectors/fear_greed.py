"""CNN 공포탐욕지수 수집기 — plan §3, T7.

fear-and-greed 파이썬 래퍼(CNN 비공식)를 사용한다. CNN 페이지 구조는 언제든
깨질 수 있으므로 graceful: 예외를 삼키지 않되(로그) None을 반환해 전체
파이프라인을 죽이지 않는다. 호출자가 None을 받아 partial_failure에 기록한다.
"""
from __future__ import annotations

import logging

from collectors.base import indicator_point

logger = logging.getLogger(__name__)


def _cnn_get():
    """외부 라이브러리 호출 경계 — 테스트가 이 지점만 대체(mock)한다.

    fear_and_greed는 import 시 requests_cache를 전역 설치해 다른 테스트의
    HTTP mock(responses)을 오염시킨다. 그래서 지연 import한다.
    """
    import fear_and_greed

    return fear_and_greed.get()


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
