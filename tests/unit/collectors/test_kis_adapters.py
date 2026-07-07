"""KIS 조회 어댑터 테스트 — plan §2, T3.

어댑터는 client.get(HTTP 경계)을 호출하고 normalize로 정규화 dict를 반환한다.
여기서는 client.get을 fixture 응답을 돌려주는 stub로 대체(경계 mock)하고,
정규화·파라미터 조립은 실제 코드로 통과한다. 현재가 계열 어댑터가 캐시를
주입받지 않는지(원칙1)도 시그니처로 고정한다.
"""
from __future__ import annotations

import inspect

import pytest

from collectors.kis import (
    balance,
    chart,
    finance_financial_ratio,
    finance_income_statement,
    inquire_price,
    multiprice,
    quote,
    stock_info,
)


class StubClient:
    """client.get 경계를 대체 — 호출 인자를 기록하고 fixture body를 반환."""

    def __init__(self, body, env="real"):
        self._body = body
        self.env = env
        self.calls = []

    def get(self, tr_id, path, params, extra_headers=None):
        self.calls.append({"tr_id": tr_id, "path": path, "params": params})
        return self._body


def test_inquire_balance_returns_normalized(load_fixture):
    client = StubClient(load_fixture("kis_inquire_balance"))
    result = balance.inquire_balance(client, "12345678", "01")

    assert result["holdings"][0]["ticker"] == "005930"
    # real env → TTTC8434R
    assert client.calls[0]["tr_id"] == "TTTC8434R"
    assert client.calls[0]["params"]["CANO"] == "12345678"


def test_inquire_balance_demo_tr_id(load_fixture):
    client = StubClient(load_fixture("kis_inquire_balance"), env="demo")
    balance.inquire_balance(client, "12345678", "01")
    assert client.calls[0]["tr_id"] == "VTTC8434R"


def test_quote_returns_normalized(load_fixture):
    client = StubClient(load_fixture("kis_asking_price"))
    result = quote.inquire_asking_price_exp_ccn(client, "005930")

    assert result["price"] == 70500.0
    assert client.calls[0]["tr_id"] == "FHKST01010200"
    assert client.calls[0]["params"]["FID_INPUT_ISCD"] == "005930"


def test_daily_chart_returns_normalized(load_fixture):
    client = StubClient(load_fixture("kis_daily_chart"))
    result = chart.inquire_daily_itemchartprice(client, "005930", "20260101", "20260703")

    assert result["candles"][0]["close"] == 70500.0
    assert client.calls[0]["tr_id"] == "FHKST03010100"
    assert client.calls[0]["params"]["FID_PERIOD_DIV_CODE"] == "D"


def test_multiprice_returns_normalized(load_fixture):
    client = StubClient(load_fixture("kis_intstock_multprice"))
    result = multiprice.intstock_multprice(client, ["005930", "000660"])

    assert len(result["items"]) == 2
    assert client.calls[0]["tr_id"] == "FHKST11300006"
    assert client.calls[0]["params"]["FID_INPUT_ISCD_1"] == "005930"
    assert client.calls[0]["params"]["FID_INPUT_ISCD_2"] == "000660"


def test_stock_info_returns_normalized(load_fixture):
    client = StubClient(load_fixture("kis_search_stock_info"))
    result = stock_info.search_stock_info(client, "005930")

    assert result["sector"] == "반도체와반도체장비"
    assert client.calls[0]["tr_id"] == "CTPF1002R"
    assert client.calls[0]["params"]["PDNO"] == "005930"


# --- inquire_price (현재가 시세, FHKST01010100) — MCP 검증 -----------------

def test_inquire_price_returns_normalized(load_fixture):
    client = StubClient(load_fixture("kis_inquire_price"))
    result = inquire_price.inquire_price(client, "005930")

    assert result["price"] == 70500.0
    assert result["per"] == 12.34
    assert result["week52_high"] == 88000.0
    # MCP 확정 TR_ID·파라미터(추측 아님).
    assert client.calls[0]["tr_id"] == "FHKST01010100"
    assert client.calls[0]["path"] == "/uapi/domestic-stock/v1/quotations/inquire-price"
    assert client.calls[0]["params"]["FID_INPUT_ISCD"] == "005930"
    assert client.calls[0]["params"]["FID_COND_MRKT_DIV_CODE"] == "J"


# --- finance_income_statement (손익계산서, FHKST66430200) — MCP 검증 --------

def test_finance_income_statement_returns_normalized(load_fixture):
    client = StubClient(load_fixture("kis_income_statement"))
    result = finance_income_statement.finance_income_statement(client, "005930")

    assert isinstance(result, list)
    assert result[0]["period"] == "202312"
    assert result[0]["revenue"] == 2589355.0
    assert client.calls[0]["tr_id"] == "FHKST66430200"
    assert client.calls[0]["path"] == "/uapi/domestic-stock/v1/finance/income-statement"
    # MCP 확정: 연도(0) 분류 + 대소문자 혼합 파라미터 키(추측 금지).
    assert client.calls[0]["params"]["FID_DIV_CLS_CODE"] == "0"
    assert client.calls[0]["params"]["fid_cond_mrkt_div_code"] == "J"
    assert client.calls[0]["params"]["fid_input_iscd"] == "005930"


# --- finance_financial_ratio (재무비율, FHKST66430300) — MCP 검증 ----------

def test_finance_financial_ratio_returns_normalized(load_fixture):
    client = StubClient(load_fixture("kis_financial_ratio"))
    result = finance_financial_ratio.finance_financial_ratio(client, "005930")

    assert isinstance(result, list)
    assert result[0]["period"] == "202312"
    assert result[0]["roe"] == 4.14
    assert result[0]["eps"] == 2131.0
    assert client.calls[0]["tr_id"] == "FHKST66430300"
    assert client.calls[0]["path"] == "/uapi/domestic-stock/v1/finance/financial-ratio"
    assert client.calls[0]["params"]["FID_DIV_CLS_CODE"] == "0"
    assert client.calls[0]["params"]["fid_cond_mrkt_div_code"] == "J"
    assert client.calls[0]["params"]["fid_input_iscd"] == "005930"


# --- 캐시 원칙1: 현재가 계열 어댑터는 캐시를 주입받지 않는다 --------------

@pytest.mark.parametrize("func", [
    quote.inquire_asking_price_exp_ccn,
    multiprice.intstock_multprice,
    balance.inquire_balance,
    inquire_price.inquire_price,  # 현재가·PER·52주 라이브 → 캐시 금지(원칙1)
])
def test_current_price_adapters_have_no_cache_param__plan_7_1(func):
    """현재가를 포함하는 어댑터 시그니처에 cache 인자가 없어야 한다."""
    params = inspect.signature(func).parameters
    assert "cache" not in params
