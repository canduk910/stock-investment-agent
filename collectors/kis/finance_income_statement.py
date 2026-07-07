"""국내주식 손익계산서 어댑터 — MCP 검증 finance_income_statement(FHKST66430200).

연도별 매출액·영업이익·당기순이익(확정 결산 데이터). 번들 오케스트레이터가
'financials' 성공 시에만 stock:meta 서브키로 캐시한다(원칙2 명시 게이트).

⚠ params 키 대소문자는 MCP 검증 코드 그대로 유지한다: FID_DIV_CLS_CODE 만
대문자, fid_cond_mrkt_div_code·fid_input_iscd 는 소문자. 추측으로 통일하면
KIS 가 파라미터 오류를 낸다(이 어댑터의 유일한 함정).
"""
from __future__ import annotations

from collectors.kis import normalize

API_PATH = "/uapi/domestic-stock/v1/finance/income-statement"
TR_ID = "FHKST66430200"  # real/demo 동일
DIV_YEAR = "0"  # 0:년 1:분기(분기는 연단위 누적합산)


def finance_income_statement(
    client, ticker: str, div_cls: str = DIV_YEAR, market: str = "J"
) -> list[dict]:
    """연도별 손익계산서 조회 → [{period, revenue, operating_income, net_income}]."""
    params = {
        "FID_DIV_CLS_CODE": div_cls,
        "fid_cond_mrkt_div_code": market,
        "fid_input_iscd": ticker,
    }
    body = client.get(TR_ID, API_PATH, params)
    return normalize.normalize_income_statement(body)
