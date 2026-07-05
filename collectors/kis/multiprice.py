"""관심종목(멀티종목) 시세조회 어댑터 — MCP 검증 intstock_multprice(FHKST11300006).

현재가를 반환하므로 캐시 금지(원칙1) — cache 인자를 받지 않는다.
한 번에 최대 30종목.
"""
from __future__ import annotations

from collectors.kis import normalize

API_PATH = "/uapi/domestic-stock/v1/quotations/intstock-multprice"
TR_ID = "FHKST11300006"
MAX_TICKERS = 30


def intstock_multprice(client, tickers: list[str], market: str = "J") -> dict:
    """복수 종목 현재가 일괄 조회 → {items:[{ticker, price, change_rate}]}."""
    if not tickers:
        raise ValueError("tickers is required (1개 이상)")
    if len(tickers) > MAX_TICKERS:
        raise ValueError(f"한 번에 최대 {MAX_TICKERS}종목까지 조회 가능")

    params: dict[str, str] = {}
    for i, ticker in enumerate(tickers, start=1):
        params[f"FID_COND_MRKT_DIV_CODE_{i}"] = market
        params[f"FID_INPUT_ISCD_{i}"] = ticker

    body = client.get(TR_ID, API_PATH, params)
    return normalize.normalize_multiprice(body)
