"""국내업종 현재지수 어댑터 — MCP 검증 inquire_index_price(FHPUP02100000).

섹터 집중도 분석용 업종 지수. FID_INPUT_ISCD 예: 0001 코스피, 1001 코스닥,
2001 코스피200(업종코드는 KIS 포탈 FAQ 참조). 지수 현재가는 실시간이라 캐시 금지.
"""
from __future__ import annotations

from collectors.kis import normalize

API_PATH = "/uapi/domestic-stock/v1/quotations/inquire-index-price"
TR_ID = "FHPUP02100000"
MARKET_SECTOR = "U"  # 업종


def inquire_index_price(client, index_code: str) -> dict:
    """업종 지수 조회 → {index_code, price, change, change_rate, ...}."""
    params = {
        "FID_COND_MRKT_DIV_CODE": MARKET_SECTOR,
        "FID_INPUT_ISCD": index_code,
    }
    body = client.get(TR_ID, API_PATH, params)
    return normalize.normalize_sector_index(body, index_code=index_code)
