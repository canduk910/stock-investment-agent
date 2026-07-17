"""라우트 공용 헬퍼 — graceful-200 응답(경계 계약: 조회/수집/요약 실패도 200 + error).

수집·색인·요약 라우트가 각자 갖던 `try: return service(...) except Exception as e:
return {**zeros, "error": str(e)[:200]}` 패턴의 단일 출처. 크래시로 프론트를 깨지 않고,
실패를 카운트 폴백 + error 필드로 표면화한다(§5.1 부분실패 보존 철학).
"""
from __future__ import annotations

from typing import Callable


def graceful_counts(fetcher: Callable[[], dict], default: dict) -> dict:
    """fetcher() 성공 시 그 결과, 예외 시 {**default, "error": str(e)[:200]}(항상 200 graceful)."""
    try:
        return fetcher()
    except Exception as e:  # 크래시 대신 안내(경계 계약: 항상 200 + error 필드)
        return {**default, "error": str(e)[:200]}
