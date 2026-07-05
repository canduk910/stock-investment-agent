"""국내업종 현재지수 어댑터 테스트 — plan §2 T4.

MCP 검증 inquire_index_price(FHPUP02100000). 업종 지수 현재가/전일대비율/
등락 종목 수를 정규화한다. 지수 현재가는 실시간 값이므로 캐시하지 않는다.
"""
from __future__ import annotations

from collectors.kis import normalize, sector_index


class StubClient:
    def __init__(self, body, env="real"):
        self._body = body
        self.env = env
        self.calls = []

    def get(self, tr_id, path, params, extra_headers=None):
        self.calls.append({"tr_id": tr_id, "path": path, "params": params})
        return self._body


def test_normalize_sector_index_shape(load_fixture):
    body = load_fixture("kis_index_price")
    result = normalize.normalize_sector_index(body, index_code="0001")

    assert result["index_code"] == "0001"
    assert result["price"] == 2750.35
    assert result["change_rate"] == 0.45
    assert result["change"] == 12.40
    assert result["advancing"] == 520
    assert result["declining"] == 330
    assert result["unchanged"] == 80


def test_sector_index_adapter(load_fixture):
    client = StubClient(load_fixture("kis_index_price"))
    result = sector_index.inquire_index_price(client, "0001")

    assert result["price"] == 2750.35
    assert client.calls[0]["tr_id"] == "FHPUP02100000"
    assert client.calls[0]["params"]["FID_COND_MRKT_DIV_CODE"] == "U"
    assert client.calls[0]["params"]["FID_INPUT_ISCD"] == "0001"
