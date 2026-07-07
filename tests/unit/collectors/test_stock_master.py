"""종목 마스터 파싱·검색·캐시 테스트 — 자동완성 데이터 계층.

.mst 고정폭 파싱(라이브 검증 포맷)과 검색 랭킹·캐시 TTL 을 고정한다. 네트워크는 fetcher 주입으로 대체.
"""
from __future__ import annotations

import json

from collectors.stock_master import load_stock_master, parse_master, search_stocks

TAIL = 228  # KOSPI


def _mst_line(ticker: str, name: str, tail: int = TAIL) -> str:
    """.mst 한 행 합성: ticker(9) + ISIN(12) + name(가변, 공백패딩) + tail 고정필드."""
    return f"{ticker:<9}" + "KR7000000000" + f"{name:<30}" + ("T" * tail)


# ── 파싱 ─────────────────────────────────────────────────────────────────────

def test_parse_extracts_ticker_name_market():
    text = _mst_line("005930", "삼성전자") + "\n" + _mst_line("000660", "SK하이닉스")
    rows = parse_master(text, TAIL, "KOSPI")
    assert rows == [
        {"ticker": "005930", "name": "삼성전자", "market": "KOSPI"},
        {"ticker": "000660", "name": "SK하이닉스", "market": "KOSPI"},
    ]


def test_parse_skips_non_6char_ticker():
    # 선물 등 6자리 아닌 코드는 제외.
    text = _mst_line("12345678", "이상한상품") + "\n" + _mst_line("068270", "셀트리온")
    rows = parse_master(text, TAIL, "KOSDAQ")
    assert [r["ticker"] for r in rows] == ["068270"]


def test_parse_skips_short_rows():
    assert parse_master("짧은행\n", TAIL, "KOSPI") == []


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
