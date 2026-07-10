"""라우트 공용 의존성 헬퍼 — 여러 {ticker} 라우트가 공유하는 진입부 검증.

지금은 ticker 정규식 검증만 둔다. 국면 판정·KIS 클라이언트 빌더 통합(_REGIME_INPUT_MAP·
build_judgement·build_kis_client)의 SSOT화는 후속(IMP-06)에서 이 모듈로 모은다.
"""
from __future__ import annotations

import re

from fastapi import HTTPException

from watchlist.models import TICKER_PATTERN  # ticker.js SSOT 와 동일 규칙(단일 출처)

_TICKER_RE = re.compile(TICKER_PATTERN)


def assert_valid_ticker(ticker: str) -> None:
    """6자 영숫자(^[0-9A-Za-z]{6}$)가 아니면 400.

    불량 코드가 KIS 조회(토큰·레이트리밋)·OpenAI 생성(비용)·히스토리 저장(파일 오염)을
    트리거하기 전에 라우트 진입부에서 차단한다. 모든 {ticker} 라우트가 이 한 함수를 공유.
    """
    if not _TICKER_RE.match(ticker or ""):
        raise HTTPException(status_code=400, detail=f"invalid ticker: {ticker}")
