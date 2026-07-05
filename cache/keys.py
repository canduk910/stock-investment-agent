"""캐시 키 컨벤션 — plan §4.

현재가는 캐시 대상이 아니므로 네임스페이스 자체를 만들지 않는다(원칙1).
"""
from __future__ import annotations


def macro_key(indicator: str) -> str:
    return f"macro:{indicator}"


def stock_meta_key(ticker: str) -> str:
    return f"stock:meta:{ticker}"


def kis_token_key(env: str) -> str:
    return f"kis:token:{env}"
