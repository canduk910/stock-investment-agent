"""SSE StreamingResponse 공용 헬퍼 — `data: {json}\\n\\n` 프레이밍 + 프록시 버퍼링 방지 헤더 SSOT.

이벤트 dict 제너레이터를 받아 text/event-stream 으로 흘린다. 제너레이터 예외는 error 프레임 후 종료
(항상 graceful — 크래시 대신 프론트가 폴백). chat SSE(`api/chat.py`)와 동일 헤더(Cloud Run 검증).
"""
from __future__ import annotations

import json
from typing import Iterable

from fastapi.responses import StreamingResponse


def _frame(ev: dict) -> str:
    return f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"


def sse_response(events: Iterable[dict]) -> StreamingResponse:
    """이벤트 제너레이터 → SSE StreamingResponse. 제너레이터 실패는 error 프레임(항상 graceful)."""

    def _stream():
        try:
            for ev in events:
                yield _frame(ev)
        except Exception as e:  # 수집/요약 제너레이터 실패 → error 프레임(크래시 금지)
            yield _frame({"type": "error", "message": str(e)[:200]})

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
