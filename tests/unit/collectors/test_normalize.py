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
