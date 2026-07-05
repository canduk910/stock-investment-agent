"""캐시 키 컨벤션 테스트 — plan §4 키 컨벤션.

macro:{indicator} / stock:meta:{ticker} / kis:token:{env}.
현재가는 네임스페이스 자체가 없다(원칙1).
"""
from __future__ import annotations

from cache import keys


def test_macro_key():
    assert keys.macro_key("T10Y2Y") == "macro:T10Y2Y"


def test_stock_meta_key():
    assert keys.stock_meta_key("005930") == "stock:meta:005930"


def test_kis_token_key():
    assert keys.kis_token_key("real") == "kis:token:real"
    assert keys.kis_token_key("demo") == "kis:token:demo"
