"""주식기본조회 어댑터 — MCP 검증 search_stock_info(CTPF1002R).

섹터·상장주식수 등 메타 정보(현재가 아님) → stock:meta:{ticker} 캐시 허용.
캐시 배선은 T8에서 policy.cache_if_clean 경유.
"""
from __future__ import annotations

from collectors.kis import normalize

API_PATH = "/uapi/domestic-stock/v1/quotations/search-stock-info"
TR_ID = "CTPF1002R"
PRDT_TYPE_STOCK = "300"  # 주식/ETF/ETN/ELW


def search_stock_info(client, ticker: str) -> dict:
    """종목 기본정보 조회 → {ticker, name, sector, listed_shares, ...}."""
    params = {
        "PRDT_TYPE_CD": PRDT_TYPE_STOCK,
        "PDNO": ticker,
    }
    body = client.get(TR_ID, API_PATH, params)
    return normalize.normalize_stock_info(body)
