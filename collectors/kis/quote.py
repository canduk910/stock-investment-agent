"""주식현재가 호가/예상체결 어댑터 — MCP 검증 inquire_asking_price_exp_ccn(FHKST01010200).

현재가·등락률을 반환하므로 캐시 금지(원칙1) — cache 인자를 받지 않는다.
"""
from __future__ import annotations

from collectors.kis import normalize

API_PATH = "/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn"
TR_ID = "FHKST01010200"  # real/demo 동일


def inquire_asking_price_exp_ccn(client, ticker: str, market: str = "J") -> dict:
    """현재가·호가 조회 → {ticker, price, change_rate, ask, bid, as_of}."""
    params = {
        "FID_COND_MRKT_DIV_CODE": market,  # J:KRX
        "FID_INPUT_ISCD": ticker,
    }
    body = client.get(TR_ID, API_PATH, params)
    return normalize.normalize_quote(body)
