"""주식현재가 시세 어댑터 — MCP 검증 inquire_price(FHKST01010100).

현재가·PER·PBR·EPS·BPS·52주 고저·시가총액 등 전부 라이브 값을 반환하므로
캐시 금지(원칙1) — cache 인자를 받지 않는다(시그니처로 강제).
real/demo 동일 TR_ID. output 은 단일 dict 로 normalize_price 가 파싱한다.
"""
from __future__ import annotations

from collectors.kis import normalize

API_PATH = "/uapi/domestic-stock/v1/quotations/inquire-price"
TR_ID = "FHKST01010100"  # real/demo 동일


def inquire_price(client, ticker: str, market: str = "J") -> dict:
    """현재가 시세 조회 → {ticker, price, change_rate, per, pbr, eps, bps,
    week52_high, week52_low, market_cap, as_of}."""
    params = {
        "FID_COND_MRKT_DIV_CODE": market,  # J:KRX
        "FID_INPUT_ISCD": ticker,
    }
    body = client.get(TR_ID, API_PATH, params)
    return normalize.normalize_price(body)
