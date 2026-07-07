"""KIS 응답 정규화 계약 테스트 — plan §2 normalize.py 규칙.

KIS 암호 필드명(stck_prpr 등) → snake_case / 숫자 문자열 → float·int 코어스
(부호·콤마) / 없는 필드 None. 실제 응답 fixture로 파싱 계약을 고정한다.
"""
from __future__ import annotations

from collectors.kis import normalize


# --- 코어스 헬퍼 -----------------------------------------------------------

def test_to_float_handles_sign_and_commas():
    assert normalize.to_float("70500") == 70500.0
    assert normalize.to_float("-1,234.5") == -1234.5
    assert normalize.to_float("") is None
    assert normalize.to_float(None) is None


def test_to_int_coerces():
    assert normalize.to_int("10") == 10
    assert normalize.to_int("5,969,782,550") == 5969782550
    assert normalize.to_int("") is None


def test_missing_field_returns_none_not_keyerror():
    # 빈 dict에서 없는 필드는 None (KeyError 금지)
    assert normalize.to_float(normalize.pick({}, "nope")) is None


# --- balance ---------------------------------------------------------------

def test_normalize_balance_shape(load_fixture):
    body = load_fixture("kis_inquire_balance")
    result = normalize.normalize_balance(body)

    assert set(result.keys()) == {"holdings", "summary"}
    assert len(result["holdings"]) == 2
    h0 = result["holdings"][0]
    assert h0["ticker"] == "005930"
    assert h0["name"] == "삼성전자"
    assert h0["qty"] == 10
    assert h0["avg_price"] == 68000.0
    assert h0["current_price"] == 70500.0
    assert h0["pnl_pct"] == 3.67
    # 손실 종목은 음수 보존
    assert result["holdings"][1]["pnl_pct"] == -2.78
    assert result["summary"]["deposit"] == 1000000.0
    assert result["summary"]["total_eval"] == 2580000.0
    assert result["summary"]["net_asset"] == 2580000.0


# --- quote (현재가/호가) ---------------------------------------------------

def test_normalize_quote_shape(load_fixture):
    body = load_fixture("kis_asking_price")
    result = normalize.normalize_quote(body)

    assert result["ticker"] == "005930"
    assert result["price"] == 70500.0
    assert result["change_rate"] == 1.20
    assert result["ask"] == 70600.0
    assert result["bid"] == 70500.0
    assert result["as_of"] == "101530"


# --- daily chart -----------------------------------------------------------

def test_normalize_daily_chart_shape(load_fixture):
    body = load_fixture("kis_daily_chart")
    result = normalize.normalize_daily_chart(body)

    assert result["ticker"] == "005930"
    assert len(result["candles"]) == 2
    c0 = result["candles"][0]
    assert c0["date"] == "20260703"
    assert c0["open"] == 70000.0
    assert c0["high"] == 70800.0
    assert c0["low"] == 69800.0
    assert c0["close"] == 70500.0
    assert c0["volume"] == 12345678


# --- multiprice ------------------------------------------------------------

def test_normalize_multiprice_shape(load_fixture):
    body = load_fixture("kis_intstock_multprice")
    result = normalize.normalize_multiprice(body)

    assert len(result["items"]) == 2
    assert result["items"][0]["ticker"] == "005930"
    assert result["items"][0]["price"] == 70500.0
    assert result["items"][0]["change_rate"] == 0.71
    assert result["items"][1]["change_rate"] == -0.85


def test_normalize_multiprice_missing_fields_are_graceful():
    """확정 필드가 없는 행은 크래시 없이 None으로 채운다(graceful, KeyError 금지)."""
    body = {"output": [{"unknown_field": "x"}]}
    result = normalize.normalize_multiprice(body)

    assert result["items"][0] == {"ticker": None, "price": None, "change_rate": None}


# --- stock info (메타) -----------------------------------------------------

def test_normalize_stock_info_shape(load_fixture):
    body = load_fixture("kis_search_stock_info")
    result = normalize.normalize_stock_info(body)

    assert result["ticker"] == "005930"
    assert result["name"] == "삼성전자"
    assert result["sector"] == "반도체와반도체장비"
    assert result["listed_shares"] == 5969782550


# --- inquire_price (현재가 시세 — 라이브 밸류에이션, FHKST01010100) ----------

def test_normalize_price_shape(load_fixture):
    """단일 output dict → 정규화 밸류에이션 필드(clean snake). raw stck_prpr 노출 금지."""
    body = load_fixture("kis_inquire_price")
    result = normalize.normalize_price(body)

    # 계약 필드명(엔진 stock/summary 가 소비) — raw KIS 명이 아니라 clean snake.
    assert set(result.keys()) == {
        "ticker", "price", "change_rate", "per", "pbr", "eps", "bps",
        "week52_high", "week52_low", "market_cap", "as_of",
    }
    assert result["ticker"] == "005930"
    assert result["price"] == 70500.0
    assert result["change_rate"] == 0.71
    assert result["per"] == 12.34
    assert result["pbr"] == 1.23
    assert result["eps"] == 5700.0
    assert result["bps"] == 57000.0
    assert result["week52_high"] == 88000.0
    assert result["week52_low"] == 49900.0
    assert result["market_cap"] == 4207000.0


def test_normalize_price_missing_fields_are_graceful():
    """필드 부재 시 None (KeyError 금지). 빈 output 도 graceful."""
    result = normalize.normalize_price({"output": {"stck_shrn_iscd": "000660"}})
    assert result["ticker"] == "000660"
    assert result["price"] is None
    assert result["per"] is None
    assert result["week52_high"] is None

    empty = normalize.normalize_price({})
    assert empty["price"] is None
    assert empty["ticker"] is None


# --- income statement (손익계산서 — FHKST66430200) --------------------------

def test_normalize_income_statement_shape(load_fixture):
    """output 리스트 → 연도별 [{period, revenue, operating_income, net_income}]."""
    body = load_fixture("kis_income_statement")
    result = normalize.normalize_income_statement(body)

    assert isinstance(result, list)
    assert len(result) == 3
    # 순서는 KIS 응답 그대로(정렬은 엔진 담당) — 최근(202312) 먼저.
    r0 = result[0]
    assert set(r0.keys()) == {"period", "revenue", "operating_income", "net_income"}
    assert r0["period"] == "202312"
    assert r0["revenue"] == 2589355.0
    assert r0["operating_income"] == 65670.0
    assert r0["net_income"] == 154871.0
    assert result[2]["period"] == "202112"
    assert result[2]["operating_income"] == 516339.0


def test_normalize_income_statement_empty_output_is_empty_list():
    """빈 output(신규상장 재무 결측) → [] (KeyError·크래시 금지)."""
    assert normalize.normalize_income_statement({"output": []}) == []
    assert normalize.normalize_income_statement({}) == []


def test_normalize_income_statement_single_dict_output_coerced_to_list():
    """output 이 단일 dict 로 오는 KIS 변형도 1원소 리스트로 정규화."""
    body = {"output": {"stac_yymm": "202312", "sale_account": "100", "bsop_prti": "10", "thtr_ntin": "5"}}
    result = normalize.normalize_income_statement(body)
    assert len(result) == 1
    assert result[0]["period"] == "202312"
    assert result[0]["revenue"] == 100.0


# --- financial ratio (재무비율 — FHKST66430300) -----------------------------

def test_normalize_financial_ratio_shape(load_fixture):
    """output 리스트 → 연도별 [{period, eps, bps, roe}]. roe 는 roe_val 에서."""
    body = load_fixture("kis_financial_ratio")
    result = normalize.normalize_financial_ratio(body)

    assert isinstance(result, list)
    assert len(result) == 3
    r0 = result[0]
    assert set(r0.keys()) == {"period", "eps", "bps", "roe"}
    assert r0["period"] == "202312"
    assert r0["eps"] == 2131.0
    assert r0["bps"] == 52068.0
    assert r0["roe"] == 4.14
    assert result[2]["roe"] == 13.92


def test_normalize_financial_ratio_empty_output_is_empty_list():
    assert normalize.normalize_financial_ratio({"output": []}) == []
    assert normalize.normalize_financial_ratio({}) == []
