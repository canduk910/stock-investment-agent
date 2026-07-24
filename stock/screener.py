"""대순환(고지로) 단계 기반 후보 종목 스크리너 — 조회 전용·판정=코드(LLM 0).

파이프라인: 시총순위 1콜로 유니버스 확보 → 종목별 일봉 병렬 조회(캡 6) → `_ma_grand_cycle` 로
현재 단계 산출. 단계 필터는 **프론트가 적용**(전 유니버스를 단계와 함께 반환)해 필터 전환 시 재조회 0.

안전: 매매 API 0(랭킹·일봉 조회만)·단계 판정=순수코드(LLM/랜덤 0)·**일봉 무캐시(원칙1)**(매 요청
라이브 재계산)·per-item graceful(한 종목 실패가 전체 안 죽임)·항상 dict(라우트 200).
"""
from __future__ import annotations

import datetime as dt

from collectors.kis import chart, ranking
from infra.parallel import fetch_parallel
from stock import constants as C
from stock.summary import grand_cycle_for_chart
from watchlist.constants import WATCHLIST_FETCH_CONCURRENCY

_LOOKBACK_DAYS = 90  # ~60 거래일 → 40-SMA + 밴드 전환창(20) 충분(60봉=단일 KIS 콜)
_FETCH_TIMEOUT = 20.0  # 종목별 일봉 병렬 상한(초)
_ADJ_PRICE = "0"  # 수정주가(액면분할 갭 제거 → 추세 연속성, 워치리스트 스파크와 동일)


def _worker_count(n: int) -> int:
    """병렬 워커 = 종목 수와 상한(WATCHLIST_FETCH_CONCURRENCY=6) 중 작은 값(KIS 유량 보호)."""
    return max(1, min(n, WATCHLIST_FETCH_CONCURRENCY))


def _fetch_cycle(client, ticker: str) -> dict | None:
    """종목 1개 일봉 → 대순환 판정 dict(또는 None: 봉<40·빈 차트). 실패는 fetch_parallel 이 None 처리."""
    today = dt.date.today()
    start = (today - dt.timedelta(days=_LOOKBACK_DAYS)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    # 현재가/일봉 캐시 신설 금지(원칙1) — 요청 시점 라이브 조회.
    result = chart.fetch_chart_series(
        client, ticker, period="D", start_date=start, end_date=end, adj_price=_ADJ_PRICE
    )
    return grand_cycle_for_chart(result)  # public 진입점(_ma_grand_cycle 래퍼)


def screen_grand_cycle(client, *, market_iscd: str = "0000", size: int = 30) -> dict:
    """시총상위 유니버스 → 종목별 대순환 현재 단계. 항상 dict(라우트 200)·판정=코드.

    반환: {candidates:[{ticker,name,price,change_rate,market_cap, stage,stage_name,arrangement,
                        band_width_pct,band_direction,bars_in_stage}],
           catalog: INDICATOR_CONFIG['grand_cycle'](6단계 라벨 SSOT),
           market_iscd, size, partial_failure:[ticker], as_of}.
    단계 필터는 응답에 미적용 — 전 유니버스를 단계와 함께 반환(프론트가 클라이언트에서 필터).
    """
    universe = ranking.market_cap_rank(client, market_iscd)[:size]
    tickers = [u["ticker"] for u in universe if u.get("ticker")]

    # 종목별 일봉 병렬(공용 fetch_parallel). 조회 실패 종목은 None + failed(partial_failure).
    jobs = {t: (lambda t=t: _fetch_cycle(client, t)) for t in tickers}
    cycles, failed = fetch_parallel(jobs, max_workers=_worker_count(len(tickers)), timeout=_FETCH_TIMEOUT)

    candidates = []
    for u in universe:
        t = u.get("ticker")
        if not t:
            continue
        gc = cycles.get(t) or {}  # None: 봉부족/조회실패 → 단계 판정 보류
        candidates.append({
            "ticker": t,
            "name": u.get("name"),
            "price": u.get("price"),
            "change_rate": u.get("change_rate"),
            "market_cap": u.get("market_cap"),
            "stage": gc.get("stage"),
            "stage_name": gc.get("stage_name"),
            "arrangement": gc.get("arrangement"),
            "band_width_pct": gc.get("band_width_pct"),
            "band_direction": gc.get("band_direction"),
            "bars_in_stage": gc.get("bars_in_stage"),
        })

    return {
        "candidates": candidates,
        "catalog": C.INDICATOR_CONFIG.get("grand_cycle"),  # 6단계 라벨 SSOT → 프론트 전파
        "market_iscd": market_iscd,
        "size": size,
        "partial_failure": failed,
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
