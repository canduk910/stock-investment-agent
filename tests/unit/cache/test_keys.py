"""캐시 키 컨벤션 테스트 — plan §4 키 컨벤션.

macro:{indicator} / stock:meta:{ticker} / kis:token:{env}.
현재가는 네임스페이스 자체가 없다(원칙1).
"""
from __future__ import annotations

from cache import keys


def test_macro_key():
    assert keys.macro_key("T10Y2Y") == "macro:T10Y2Y"


def test_stock_meta_key():
    assert keys.stock_meta_key("005930") == "stock:meta:005930"


def test_stock_meta_sub_key():
    # 섹션 서브키 — stock:meta: 프리픽스 유지로 캐시 정책(원칙1 화이트리스트) 통과.
    assert keys.stock_meta_sub_key("005930", "financials") == "stock:meta:005930:financials"
    assert keys.stock_meta_sub_key("000660", "basic") == "stock:meta:000660:basic"
    # 상위 stock_meta_key 와 프리픽스 스킴이 단일하다(정책 화이트리스트 정합).
    assert keys.stock_meta_sub_key("005930", "basic").startswith(keys.stock_meta_key("005930"))


def test_kis_token_key_isolates_by_app_key():
    # 프리픽스 유지(정책 통과) + env·app_key 별 격리.
    k1 = keys.kis_token_key("real", "APPKEY-A")
    k2 = keys.kis_token_key("real", "APPKEY-B")
    k3 = keys.kis_token_key("demo", "APPKEY-A")
    assert k1.startswith("kis:token:real:") and k3.startswith("kis:token:demo:")
    assert k1 != k2 != k3 and k1 != k3  # 앱키·env 다르면 키 다름
    assert "APPKEY-A" not in k1  # 원문 미노출(해시)
    assert keys.kis_token_key("real", "APPKEY-A") == k1  # 결정적
