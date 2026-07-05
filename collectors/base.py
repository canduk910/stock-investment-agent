"""외부 지표 공통 반환 계약 — plan §3.

모든 매크로 지표 수집기는 IndicatorPoint(dict)로 반환한다:
{"key", "value": float, "as_of": date, "source", "prev_value"}.
prev_value는 [P2] 모멘텀 확장용 훅(기본 None).
"""
from __future__ import annotations

import datetime as dt
from typing import Any


def indicator_point(
    key: str,
    value: float | None,
    as_of: dt.date | None,
    source: str,
    prev_value: float | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "value": value,
        "as_of": as_of,
        "source": source,
        "prev_value": prev_value,
    }
