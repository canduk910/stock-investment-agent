"""국내주식 재무비율 어댑터 — MCP 검증 finance_financial_ratio(FHKST66430300).

연도별 EPS·BPS·ROE. avg_per 근사(EPS × 결산기말 종가)의 EPS 원천이다.
번들 오케스트레이터가 'financials' 성공 시에만 캐시한다(원칙2).

⚠ params 키 대소문자는 MCP 검증 코드 그대로: FID_DIV_CLS_CODE 만 대문자,
fid_cond_mrkt_div_code·fid_input_iscd 는 소문자(추측 통일 금지).
"""
from __future__ import annotations

from collectors.kis import normalize

API_PATH = "/uapi/domestic-stock/v1/finance/financial-ratio"
TR_ID = "FHKST66430300"  # real/demo 동일
DIV_YEAR = "0"  # 0:년 1:분기


def finance_financial_ratio(
    client, ticker: str, div_cls: str = DIV_YEAR, market: str = "J"
) -> list[dict]:
    """연도별 재무비율 조회 → [{period, eps, bps, roe}]."""
    params = {
        "FID_DIV_CLS_CODE": div_cls,
        "fid_cond_mrkt_div_code": market,
        "fid_input_iscd": ticker,
    }
    body = client.get(TR_ID, API_PATH, params)
    return normalize.normalize_financial_ratio(body)
