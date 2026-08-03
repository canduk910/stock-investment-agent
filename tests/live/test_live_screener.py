"""대순환 후보 스크리너 라이브 게이트 — 실 KIS 키로만 도는 검증(@pytest.mark.live).

프로젝트 규약: **신규 KIS 어댑터는 라이브로 필드명·행수·real/demo 를 확정**한다(순위 API 는 real 전용
경향). 시총순위 어댑터가 종목코드+이름을 주는지, 스크리너가 실 종목의 대순환 단계를 산출하는지 확인.
기본 실행에서 제외(-m live · real 키 필요).
"""
from __future__ import annotations

import pytest

from collectors.kis import ranking
from infra.config import ConfigError, KisConfig
from stock.screener import screen_grand_cycle

pytestmark = pytest.mark.live


def _client_or_skip():
    try:
        from cache.local import FileCache
        from collectors.kis import auth
        from collectors.kis.client import KisClient

        config = KisConfig.load()
        cache = FileCache(".cache/kis_token.json")
        provider = auth.make_token_provider(config, cache)
        return KisClient(config, provider)
    except ConfigError as exc:
        pytest.skip(f"KIS 키 없음: {exc}")


def test_live_market_cap_rank_fields():
    """시총순위 API 가 종목코드+이름+시총 을 담은 리스트를 주는지(필드명 확정)."""
    client = _client_or_skip()
    rows = ranking.market_cap_rank(client, iscd="2001")  # 코스피200
    assert len(rows) >= 5, f"순위 행이 너무 적음: {len(rows)}"
    top = rows[0]
    assert top["ticker"] and len(top["ticker"]) == 6, f"종목코드 형식 이상: {top['ticker']}"
    assert top["name"], "종목명(hts_kor_isnm) 결측 — 필드명 확인 필요"
    assert top["market_cap"] and top["market_cap"] > 0, "시가총액(stck_avls) 결측"


def test_live_screen_grand_cycle_produces_stages():
    """스크리너가 실 종목의 대순환 단계(1~6)를 산출하고 종목명을 붙이는지(end-to-end)."""
    client = _client_or_skip()
    out = screen_grand_cycle(client, market_iscd="2001", size=10)
    cands = out["candidates"]
    assert len(cands) >= 5, f"후보가 너무 적음: {len(cands)}"
    # 종목명 반드시 포함(사용자 핵심 요구)
    assert all(c["name"] for c in cands), "일부 후보 종목명 결측"
    # 대다수는 40봉 이상이라 단계 산출됨(1~6). None 은 봉부족만.
    staged = [c for c in cands if c["stage"] is not None]
    assert len(staged) >= 3, f"단계 산출 종목이 너무 적음(봉부족 과다?): {len(staged)}"
    for c in staged:
        assert c["stage"] in (1, 2, 3, 4, 5, 6)
        assert c["stage_name"]  # 6단계 라벨 SSOT
    assert out["catalog"] and len(out["catalog"]["stages"]) == 6


def test_live_scan_all_end_to_end_small_universe():
    """배치 스캐너(scan_all)가 실 KIS 로 소수 종목 대순환 단계를 산출·저장하는지(end-to-end).

    전체 유니버스(~2.5천 종목·수 분)는 라이브에서 돌리지 않고 대표 4종목만(레이트리밋 보호).
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from infra.db import Base, import_models
    from stock.screener_scan import scan_all
    from stock.screener_store import ScreenerResultStore

    client = _client_or_skip()
    import_models()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    store = ScreenerResultStore(session_factory=sessionmaker(bind=engine, expire_on_commit=False))

    universe = [
        {"ticker": "005930", "name": "삼성전자", "market": "KOSPI"},
        {"ticker": "000660", "name": "SK하이닉스", "market": "KOSPI"},
        {"ticker": "035720", "name": "카카오", "market": "KOSPI"},
        {"ticker": "247540", "name": "에코프로비엠", "market": "KOSDAQ"},
    ]
    counts = scan_all(client, store, universe=universe, as_of_date="2099-01-01", concurrency=3)
    assert counts["total"] == 4 and counts["scanned"] == 4
    assert counts["with_stage"] >= 3, f"단계 산출 종목 부족: {counts}"
    assert counts["failed"] == 0

    rows = store.list_results()
    assert store.latest_as_of() == "2099-01-01"
    by = {r["ticker"]: r for r in rows}
    assert set(by) == {"005930", "000660", "035720", "247540"}
    for r in rows:
        if r["stage"] is not None:
            assert r["stage"] in (1, 2, 3, 4, 5, 6) and r["stage_name"]
        assert "price" not in r and "change_rate" not in r  # 무캐시(현재가 미저장)


def test_live_common_stocks_universe_scale():
    """보통주 유니버스가 현실적 규모(~2천대 종목)이고 우선주/ETF 브랜드가 새지 않는지."""
    from collectors.stock_master import load_stock_master
    from stock.universe import common_stocks

    common = common_stocks(load_stock_master())
    assert 1800 <= len(common) <= 3000, f"유니버스 규모 이상: {len(common)}"
    names = [s["name"] for s in common]
    for junk in ("KODEX", "TIGER", "KIWOOM"):  # 대표 ETF 브랜드 접두는 없어야
        assert not any(n.upper().startswith(junk) for n in names), f"{junk} ETF 누수"
    assert not any(s["ticker"][-1] != "0" for s in common), "우선주(끝자리≠0) 누수"
