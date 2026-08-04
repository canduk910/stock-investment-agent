"""종목 마스터 파싱·검색·캐시 테스트 — 자동완성 데이터 계층.

.mst 고정폭 파싱(라이브 검증 포맷)과 검색 랭킹·캐시 TTL 을 고정한다. 네트워크는 fetcher 주입으로 대체.
"""
from __future__ import annotations

import json

import pytest

from collectors.stock_master import load_stock_master, parse_master, search_stocks

TAIL = 228  # KOSPI


def _mst_line(ticker: str, name: str, sec: str = "ST", tail: int = TAIL) -> str:
    """.mst 한 행 합성: ticker(9) + ISIN(12) + name(가변, 공백패딩) + tail 고정필드.

    tail(part2) 고정필드는 **선두 패딩 1칸 + 증권그룹구분코드(2) + 나머지**로 채운다 —
    라이브 검증된 실제 오프셋(그룹코드는 part2 선두 1칸 뒤 2글자)을 합성 데이터에 반영.
    """
    part2 = " " + f"{sec:<2}"[:2] + ("T" * (tail - 3))
    return f"{ticker:<9}" + "KR7000000000" + f"{name:<30}" + part2


# ── 파싱 ─────────────────────────────────────────────────────────────────────

def test_parse_extracts_ticker_name_market():
    # additive: 기존 ticker/name/market 계약 불변 + sec_group 추가.
    text = _mst_line("005930", "삼성전자", sec="ST") + "\n" + _mst_line("000660", "SK하이닉스", sec="ST")
    rows = parse_master(text, TAIL, "KOSPI")
    assert rows == [
        {"ticker": "005930", "name": "삼성전자", "market": "KOSPI", "sec_group": "ST"},
        {"ticker": "000660", "name": "SK하이닉스", "market": "KOSPI", "sec_group": "ST"},
    ]


def test_parse_preserves_core_fields_additive():
    # sec_group 추가가 core 3필드(ticker/name/market) 값을 건드리지 않음을 명시.
    (row,) = parse_master(_mst_line("069500", "KODEX 200", sec="EF"), TAIL, "KOSPI")
    assert row["ticker"] == "069500"
    assert row["name"] == "KODEX 200"
    assert row["market"] == "KOSPI"
    assert row["sec_group"] == "EF"


def test_parse_extracts_sec_group_offset_kospi_and_kosdaq():
    # 그룹코드 오프셋은 시장별 tail(KOSPI 228·KOSDAQ 222)이 달라도 동일 규칙(part2 선두+1).
    (kospi,) = parse_master(_mst_line("005930", "삼성전자", sec="ST", tail=228), 228, "KOSPI")
    (kosdaq,) = parse_master(_mst_line("247540", "에코프로비엠", sec="ST", tail=222), 222, "KOSDAQ")
    assert kospi["sec_group"] == "ST"
    assert kosdaq["sec_group"] == "ST"
    # ETF/ETN/리츠 코드도 각각 추출.
    (etf,) = parse_master(_mst_line("069500", "KODEX 200", sec="EF"), 228, "KOSPI")
    (etn,) = parse_master(_mst_line("530031", "삼성 레버리지 WTI원유 선물 ETN", sec="EN"), 228, "KOSPI")
    (reit,) = parse_master(_mst_line("330590", "롯데리츠", sec="RT"), 228, "KOSPI")
    assert (etf["sec_group"], etn["sec_group"], reit["sec_group"]) == ("EF", "EN", "RT")


def test_parse_sec_group_none_when_malformed():
    # 그룹코드 자리가 2글자 알파가 아니면(구 포맷·손상) None graceful — core 필드는 유지.
    part2 = "  99" + ("T" * (TAIL - 4))  # 선두+1 위치가 "99"(비알파)
    row = f"{'005930':<9}" + "KR7000000000" + f"{'삼성전자':<30}" + part2
    (parsed,) = parse_master(row, TAIL, "KOSPI")
    assert parsed["ticker"] == "005930"
    assert parsed["name"] == "삼성전자"
    assert parsed["sec_group"] is None


def test_parse_skips_non_6char_ticker():
    # 선물 등 6자리 아닌 코드는 제외.
    text = _mst_line("12345678", "이상한상품") + "\n" + _mst_line("068270", "셀트리온")
    rows = parse_master(text, TAIL, "KOSDAQ")
    assert [r["ticker"] for r in rows] == ["068270"]


def test_parse_skips_short_rows():
    assert parse_master("짧은행\n", TAIL, "KOSPI") == []


# ── 라이브(실 마스터 다운로드) 그룹코드 대조 ──────────────────────────────────

@pytest.mark.live
def test_live_master_sec_group_matches_known_tickers():
    """실 마스터를 내려받아 대표 티커의 증권그룹구분코드를 대조(추측 아님·오프셋 회귀 방지)."""
    from collectors.stock_master import _fetch_all  # 네트워크(라이브 전용)

    master = _fetch_all()
    by_ticker = {r["ticker"]: r for r in master}
    assert by_ticker["005930"]["sec_group"] == "ST"   # 삼성전자 = 주권
    assert by_ticker["069500"]["sec_group"] == "EF"   # KODEX 200 = ETF
    assert by_ticker["330590"]["sec_group"] == "RT"   # 롯데리츠 = 리츠
    assert by_ticker["005935"]["sec_group"] == "ST"   # 삼성전자우 = 주권(우선주도 ST)


# ── 검색 ─────────────────────────────────────────────────────────────────────

_MASTER = [
    {"ticker": "005930", "name": "삼성전자", "market": "KOSPI"},
    {"ticker": "006400", "name": "삼성SDI", "market": "KOSPI"},
    {"ticker": "028260", "name": "삼성물산", "market": "KOSPI"},
    {"ticker": "000660", "name": "SK하이닉스", "market": "KOSPI"},
    {"ticker": "247540", "name": "에코프로비엠", "market": "KOSDAQ"},
]


def test_search_by_name_prefix_kospi_first():
    r = search_stocks(_MASTER, "삼성")
    names = [s["name"] for s in r]
    assert set(names) == {"삼성전자", "삼성SDI", "삼성물산"}
    assert all(s["market"] == "KOSPI" for s in r)


def test_search_by_substring():
    r = search_stocks(_MASTER, "하이닉스")
    assert [s["ticker"] for s in r] == ["000660"]


def test_search_ranks_shorter_name_first():
    # 파생상품(긴 이름)보다 정식 종목(짧은 이름)이 먼저 — "하이닉스" 검색 UX 핵심.
    m = [
        {"ticker": "0193T0", "name": "KODEX SK하이닉스단일종목레버리지", "market": "KOSPI"},
        {"ticker": "000660", "name": "SK하이닉스", "market": "KOSPI"},
    ]
    assert search_stocks(m, "하이닉스")[0]["ticker"] == "000660"


def test_search_by_ticker_prefix():
    r = search_stocks(_MASTER, "005930")
    assert r[0]["name"] == "삼성전자"


def test_search_limit():
    assert len(search_stocks(_MASTER, "삼성", limit=2)) == 2


def test_search_empty_query():
    assert search_stocks(_MASTER, "  ") == []


# ── 캐시 (TTL·주입) ──────────────────────────────────────────────────────────

def test_load_uses_fresh_cache_without_fetch(tmp_path):
    cache = tmp_path / "m.json"
    cache.write_text(json.dumps({"as_of": 1000, "stocks": [{"ticker": "005930", "name": "삼성전자", "market": "KOSPI"}]}), encoding="utf-8")

    def _boom():
        raise AssertionError("신선 캐시인데 재수집하면 안 됨")

    got = load_stock_master(str(cache), ttl_seconds=100, fetcher=_boom, now=lambda: 1050)
    assert got[0]["ticker"] == "005930"


def test_load_refetches_when_stale(tmp_path):
    cache = tmp_path / "m.json"
    cache.write_text(json.dumps({"as_of": 1000, "stocks": [{"ticker": "old", "name": "old", "market": "KOSPI"}]}), encoding="utf-8")
    fresh = [{"ticker": "000660", "name": "SK하이닉스", "market": "KOSPI"}]

    got = load_stock_master(str(cache), ttl_seconds=100, fetcher=lambda: fresh, now=lambda: 9999)
    assert got == fresh
    # 캐시도 갱신됐는지.
    assert json.loads(cache.read_text(encoding="utf-8"))["stocks"] == fresh


def test_load_fetches_when_missing(tmp_path):
    fresh = [{"ticker": "247540", "name": "에코프로비엠", "market": "KOSDAQ"}]
    got = load_stock_master(str(tmp_path / "none.json"), fetcher=lambda: fresh, now=lambda: 1)
    assert got == fresh
