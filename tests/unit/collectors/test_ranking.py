"""KIS 시가총액 상위 순위 어댑터 + normalizer 테스트 — 스크리너 유니버스 확보.

어댑터는 client.get(HTTP 경계)만 호출하고 normalize로 리스트를 반환한다. 경계 stub로 대체하고
파라미터 조립(소문자 키·시장 iscd)·정규화는 실제 코드로 통과. 조회 전용(캐시 인자 없음).
"""
from __future__ import annotations

from collectors.kis import normalize, ranking


class StubClient:
    def __init__(self, body):
        self._body = body
        self.calls = []

    def get(self, tr_id, path, params, extra_headers=None):
        self.calls.append({"tr_id": tr_id, "path": path, "params": params})
        return self._body


_FAKE_BODY = {
    "output": [
        {"mksc_shrn_iscd": "005930", "data_rank": "1", "hts_kor_isnm": "삼성전자",
         "stck_prpr": "78,000", "prdy_ctrt": "1.20", "stck_avls": "465,000,000", "acml_vol": "10000000"},
        {"mksc_shrn_iscd": "000660", "data_rank": "2", "hts_kor_isnm": "SK하이닉스",
         "stck_prpr": "180,000", "prdy_ctrt": "-0.85", "stck_avls": "130,000,000"},
    ]
}


def test_normalize_market_cap_rank_shape():
    result = normalize.normalize_market_cap_rank(_FAKE_BODY)
    assert len(result) == 2
    r0 = result[0]
    assert r0["ticker"] == "005930" and r0["name"] == "삼성전자"
    assert r0["rank"] == 1 and r0["price"] == 78000.0
    assert r0["change_rate"] == 1.20 and r0["market_cap"] == 465000000.0
    assert result[1]["ticker"] == "000660" and result[1]["change_rate"] == -0.85


def test_normalize_market_cap_rank_missing_fields_graceful():
    result = normalize.normalize_market_cap_rank({"output": [{"unknown": "x"}]})
    assert result[0] == {
        "ticker": None, "name": None, "rank": None,
        "price": None, "change_rate": None, "market_cap": None,
    }


def test_normalize_market_cap_rank_empty():
    assert normalize.normalize_market_cap_rank({}) == []
    assert normalize.normalize_market_cap_rank({"output": None}) == []


def test_market_cap_rank_adapter_params_and_result():
    client = StubClient(_FAKE_BODY)
    result = ranking.market_cap_rank(client, iscd="2001")
    assert result[0]["ticker"] == "005930" and result[0]["name"] == "삼성전자"
    call = client.calls[0]
    assert call["tr_id"] == "FHPST01740000"
    assert call["path"] == "/uapi/domestic-stock/v1/ranking/market-cap"
    # ⚠ 소문자 키(MCP 확정) + 시장 iscd 반영 + 고정 Unique key
    assert call["params"]["fid_input_iscd"] == "2001"
    assert call["params"]["fid_cond_scr_div_code"] == "20174"
    assert call["params"]["fid_cond_mrkt_div_code"] == "J"
    assert call["params"]["fid_div_cls_code"] == "0"


def test_market_cap_rank_default_iscd_is_all():
    client = StubClient(_FAKE_BODY)
    ranking.market_cap_rank(client)
    assert client.calls[0]["params"]["fid_input_iscd"] == "0000"


def test_market_iscd_mapping():
    assert ranking.MARKET_ISCD == {
        "all": "0000", "kospi": "0001", "kosdaq": "1001", "kospi200": "2001",
    }
