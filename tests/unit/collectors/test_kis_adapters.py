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


# ── fetch_chart_series: ~100/호출 상한 date-window 후진 페이지네이션 ───────────

class PagingStubClient:
    """KIS 페이지네이션 모사 — 전체 날짜셋을 갖고, [DATE_1, DATE_2] 중 **최근 page개**만 반환.

    실제 KIS 처럼 한 호출당 상한(page)을 넘지 않는다. 호출 인자를 calls 에 기록.
    """

    def __init__(self, all_dates, page=100, env="real"):
        self.all = sorted(all_dates)  # 오름차순 YYYYMMDD
        self.page = page
        self.env = env
        self.calls = []

    def get(self, tr_id, path, params, extra_headers=None):
        self.calls.append(params)
        start, end = params["FID_INPUT_DATE_1"], params["FID_INPUT_DATE_2"]
        eligible = [d for d in self.all if start <= d <= end]
        window = eligible[-self.page :]  # 최근 page개(상한)
        return {
            "output1": {"stck_shrn_iscd": "005930"},
            "output2": [
                {"stck_bsop_date": d, "stck_oprc": "1", "stck_hgpr": "1",
                 "stck_lwpr": "1", "stck_clpr": "100", "acml_vol": "1000"}
                for d in window
            ],
        }


def _date_range(n):
    """오름차순 YYYYMMDD n개(2020-01-01부터 일 단위)."""
    base = __import__("datetime").date(2020, 1, 1)
    td = __import__("datetime").timedelta
    return [(base + td(days=i)).strftime("%Y%m%d") for i in range(n)]


def test_fetch_chart_series_single_page_one_call():
    dates = _date_range(60)  # 100 미만 → 1콜로 충분
    client = PagingStubClient(dates, page=100)
    result = chart.fetch_chart_series(
        client, "005930", period="D", start_date=dates[0], end_date=dates[-1]
    )
    assert len(result["candles"]) == 60
    assert len(client.calls) == 1  # 페이지네이션 불필요
    got = [c["date"] for c in result["candles"]]
    assert got == sorted(got)  # date 오름차순


def test_fetch_chart_series_paginates_backward_and_merges():
    dates = _date_range(250)  # 100 상한 → 3콜(100+100+50)
    client = PagingStubClient(dates, page=100)
    result = chart.fetch_chart_series(
        client, "005930", period="D", start_date=dates[0], end_date=dates[-1]
    )
    assert len(result["candles"]) == 250  # 전 구간 병합
    assert len(client.calls) == 3
    got = [c["date"] for c in result["candles"]]
    assert got == dates  # 중복 제거·정렬 완전 복원


def test_fetch_chart_series_respects_max_pages_cap():
    dates = _date_range(250)
    client = PagingStubClient(dates, page=100)
    result = chart.fetch_chart_series(
        client, "005930", period="D", start_date=dates[0], end_date=dates[-1], max_pages=2
    )
    assert len(client.calls) == 2  # 캡에서 중단
    assert len(result["candles"]) == 200  # 2페이지분만


def test_fetch_chart_series_stops_on_no_progress():
    # cursor 를 무시하고 항상 같은 윈도우를 주는 stub → 무진행 감지로 2콜 후 종료(무한루프 방지).
    class StuckClient(PagingStubClient):
        def get(self, tr_id, path, params, extra_headers=None):
            self.calls.append(params)
            window = self.all[-self.page :]  # 항상 최근 100(cursor 무시)
            return {
                "output1": {"stck_shrn_iscd": "005930"},
                "output2": [
                    {"stck_bsop_date": d, "stck_oprc": "1", "stck_hgpr": "1",
                     "stck_lwpr": "1", "stck_clpr": "100", "acml_vol": "1000"}
                    for d in window
                ],
            }

    dates = _date_range(250)
    client = StuckClient(dates, page=100)
    result = chart.fetch_chart_series(
        client, "005930", period="D", start_date=dates[0], end_date=dates[-1]
    )
    assert len(client.calls) == 2  # 1콜 수집 → 2콜째 새 데이터 0 → 종료
    assert len(result["candles"]) == 100


def test_fetch_chart_series_forwards_period_and_adj():
    dates = _date_range(30)
    client = PagingStubClient(dates, page=100)
    chart.fetch_chart_series(
        client, "005930", period="W", start_date=dates[0], end_date=dates[-1], adj_price="0"
    )
    assert client.calls[0]["FID_PERIOD_DIV_CODE"] == "W"
    assert client.calls[0]["FID_ORG_ADJ_PRC"] == "0"


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
