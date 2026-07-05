"""라이브 스모크 테스트 — plan §5, §7, T9.

실 API 키로 실제 조회를 확인한다. @pytest.mark.live 로 분리돼 기본 실행
(-m 'not live')에서 제외되므로, 키 없는 CI/QA에서도 전체 스위트가 green이다.
실행: `uv run pytest -m live`.

키가 없으면 ConfigError를 skip으로 처리해 라이브 실행 시에도 명확히 넘어간다.
"""
from __future__ import annotations

import datetime as dt

import pytest

from infra.config import ConfigError, KisConfig, fred_api_key

pytestmark = pytest.mark.live


def _kis_client():
    from cache.local import FileCache
    from collectors.kis import auth
    from collectors.kis.client import KisClient

    config = KisConfig.load()
    cache = FileCache(".cache/kis_token.json")
    token_provider = auth.make_token_provider(config, cache)
    return KisClient(config, token_provider), config


def test_live_kis_balance():
    try:
        client, config = _kis_client()
    except ConfigError as exc:
        pytest.skip(f"KIS 키 없음: {exc}")

    if not config.account_no:
        pytest.skip("KIS_ACCOUNT_NO 미설정")

    cano, _, prdt = config.account_no.partition("-")
    from collectors.kis import balance

    result = balance.inquire_balance(client, cano, prdt or "01")
    assert isinstance(result["holdings"], list)
    assert "summary" in result


def test_live_kis_multiprice_confirms_field_mapping():
    """intstock_multprice 실필드명 확정 게이트 (명세 §4 미해결 항목).

    normalize_multiprice는 output 필드명(inter_shrn_iscd/inter2_prpr 등)이
    KIS 문서 표준명 기반 추정이라 후보키로 방어조회 중이다. 실 응답에서
    ticker/price가 실제로 채워지는지 확인한다. 필드명이 틀리면 None이 되어
    이 테스트가 실패하며, 그때 후보키를 실필드명으로 좁히고 fixture를 교체한다.
    """
    try:
        client, _ = _kis_client()
    except ConfigError as exc:
        pytest.skip(f"KIS 키 없음: {exc}")

    from collectors.kis import multiprice

    result = multiprice.intstock_multprice(client, ["005930"])  # 삼성전자
    assert result["items"], "items가 비어있음 — output 섹션 키 매핑 확인 필요"
    item = result["items"][0]
    assert item["ticker"] is not None, (
        "ticker 필드명 매핑 실패 — inter_shrn_iscd/mksc_shrn_iscd 후보키를 실필드명으로 갱신 필요"
    )
    assert isinstance(item["price"], float), (
        "price 필드명 매핑 실패 — inter2_prpr/stck_prpr 후보키를 실필드명으로 갱신 필요"
    )


def test_live_fred_t10y2y():
    try:
        key = fred_api_key()
    except ConfigError as exc:
        pytest.skip(f"FRED 키 없음: {exc}")

    from collectors import fred

    point = fred.fetch_t10y2y(key)
    assert isinstance(point["value"], float)
    assert isinstance(point["as_of"], dt.date)


def test_live_vix():
    try:
        key = fred_api_key()
    except ConfigError as exc:
        pytest.skip(f"FRED 키 없음: {exc}")

    from collectors import vix

    point = vix.fetch_vix(fred_api_key=key)
    assert isinstance(point["value"], float)
    assert point["source"] in ("yahoo", "fred")


def test_live_fear_greed():
    from collectors import fear_greed

    point = fear_greed.fetch_fear_greed()
    # graceful: 성공이면 IndicatorPoint, CNN 구조 변경이면 None (둘 다 허용)
    assert point is None or isinstance(point["value"], float)
