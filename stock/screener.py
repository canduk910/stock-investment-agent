"""대순환(고지로) 단계 기반 후보 종목 스크리너 — 조회 전용·판정=코드(LLM 0).

파이프라인: 시총순위 1콜로 유니버스 확보 → 종목별 일봉 병렬 조회(캡 6) → `_ma_grand_cycle` 로
현재 단계 산출. 단계 필터는 **프론트가 적용**(전 유니버스를 단계와 함께 반환)해 필터 전환 시 재조회 0.

안전: 매매 API 0(랭킹·일봉 조회만)·단계 판정=순수코드(LLM/랜덤 0)·**일봉 무캐시(원칙1)**(매 요청
라이브 재계산)·per-item graceful(한 종목 실패가 전체 안 죽임)·항상 dict(라우트 200).
"""
from __future__ import annotations

import datetime as dt

from collectors.kis import chart, finance_financial_ratio, inquire_price, ranking
from infra.parallel import fetch_parallel
from infra.timeutil import now_iso  # as_of 타임스탬프 — timeutil SSOT(인라인 datetime 조립 제거)
from stock import constants as C
from stock.financial_score import _latest_annual_row
from stock.summary import _avg_per, grand_cycle_for_chart
from watchlist.constants import WATCHLIST_FETCH_CONCURRENCY

_LOOKBACK_DAYS = 90  # ~60 거래일 → 40-SMA + 밴드 전환창(20) 충분(60봉=단일 KIS 콜)
_FETCH_TIMEOUT = 20.0  # 종목별 일봉 병렬 상한(초)
_ADJ_PRICE = "0"  # 수정주가(액면분할 갭 제거 → 추세 연속성, 워치리스트 스파크와 동일)
_SPARK_POINTS = 30  # 미니차트 표시 최근 종가 개수(스캔 일봉에서 파생)
_YEAR_END_ADJ_PRICE = "1"  # 결산가(월봉)는 원주가 — EPS(원주가 기준)와 조정기준 일치(avg_per, 번들과 동일)


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


def _year_end_prices(client, ticker: str, ratio: list[dict]) -> dict:
    """재무비율 결산기(period) → 결산기말 종가(월봉 단일 콜). avg_per 용(원주가·EPS 조정기준 일치)."""
    periods = {str(r.get("period")) for r in (ratio or []) if r.get("period")}
    years = sorted({p[:4] for p in periods if len(p) >= 4})
    if not years:
        return {}
    today = dt.date.today().strftime("%Y%m%d")
    monthly = chart.inquire_daily_itemchartprice(
        client, ticker, f"{years[0]}0101", today, period="M", adj_price=_YEAR_END_ADJ_PRICE
    )
    month_close: dict = {}
    for candle in monthly.get("candles") or []:
        d = candle.get("date")
        close = candle.get("close")
        if d and len(str(d)) >= 6 and close is not None:
            month_close[str(d)[:6]] = close
    return {p: month_close[p] for p in periods if p in month_close}


def fetch_scan_metrics(client, ticker: str) -> dict:
    """배치 스캔용 종목 지표 수집(4콜) — 대순환 + 스파크 + 시총 + 재무 3축 + avg_per.

    조회 전용·판정=코드·무캐시(일봉/현재가). **per-call graceful**: 일봉(대순환·1차)만
    실패 시 예외 전파(그 종목=failed), 시총·재무·avg_per 는 개별 try 로 실패해도 나머지 보존.
    저장 스냅샷 필드만 반환 — 현재가·현재 PER 은 담지 않는다(무캐시 원칙1·서빙이 라이브).
    """
    row = {
        "stage": None, "stage_name": None, "arrangement": None,
        "band_width_pct": None, "band_direction": None, "bars_in_stage": None,
        "spark": None, "market_cap": None,
        "roe": None, "net_income_growth": None, "debt_ratio": None, "avg_per": None,
    }

    # 1) 일봉(단일 콜) → 대순환 단계 + 스파크(부산물). 실패는 그 종목 failed(예외 전파).
    today = dt.date.today()
    start = (today - dt.timedelta(days=_LOOKBACK_DAYS)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    daily = chart.fetch_chart_series(
        client, ticker, period="D", start_date=start, end_date=end, adj_price=_ADJ_PRICE
    )
    gc = grand_cycle_for_chart(daily) or {}
    for k in ("stage", "stage_name", "arrangement", "band_width_pct", "band_direction", "bars_in_stage"):
        row[k] = gc.get(k)
    closes = [c.get("close") for c in (daily.get("candles") or []) if c.get("close") is not None]
    if len(closes) >= 2:
        row["spark"] = closes[-_SPARK_POINTS:]

    # 2) 현재가(단일 콜) → 시가총액(정렬키). 실패해도 나머지 보존.
    try:
        val = inquire_price.inquire_price(client, ticker)
        row["market_cap"] = val.get("market_cap")
    except Exception:  # noqa: BLE001 — 시총 조회 실패는 graceful(정렬만 밀림)
        pass

    # 3) 재무비율(단일 콜) → 최신 연간 3축(수익성·성장성·안정성) + 4) avg_per(월봉 결산가).
    try:
        ratio = finance_financial_ratio.finance_financial_ratio(client, ticker)
        latest = _latest_annual_row(ratio)
        row["roe"] = latest.get("roe")
        row["net_income_growth"] = latest.get("net_income_growth")
        row["debt_ratio"] = latest.get("debt_ratio")
        try:
            avg, _ = _avg_per(ratio, _year_end_prices(client, ticker, ratio))
            row["avg_per"] = avg
        except Exception:  # noqa: BLE001 — 월봉/avg_per 실패는 graceful(밸류 축만 결측)
            pass
    except Exception:  # noqa: BLE001 — 재무비율 실패는 graceful(3축 결측·재정규화)
        pass

    return row


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
        "as_of": now_iso(),
    }
