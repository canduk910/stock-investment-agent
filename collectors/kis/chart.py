"""국내주식기간별시세(일/주/월/년) 어댑터 — MCP 검증 inquire_daily_itemchartprice(FHKST03010100).

일봉은 확정 과거 데이터라 조건부 캐시 가능(현재가 아님). 캐시 배선은 T8에서 정책 경유.
"""
from __future__ import annotations

from collectors.kis import normalize

API_PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
TR_ID = "FHKST03010100"  # real/demo 동일


def inquire_daily_itemchartprice(
    client,
    ticker: str,
    start_date: str,
    end_date: str,
    period: str = "D",
    adj_price: str = "1",
    market: str = "J",
) -> dict:
    """기간별 시세(캔들) 조회 → {ticker, candles:[...]}."""
    params = {
        "FID_COND_MRKT_DIV_CODE": market,
        "FID_INPUT_ISCD": ticker,
        "FID_INPUT_DATE_1": start_date,
        "FID_INPUT_DATE_2": end_date,
        "FID_PERIOD_DIV_CODE": period,  # D:일 W:주 M:월 Y:년
        "FID_ORG_ADJ_PRC": adj_price,   # 0:수정주가 1:원주가
    }
    body = client.get(TR_ID, API_PATH, params)
    return normalize.normalize_daily_chart(body)
