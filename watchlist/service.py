"""워치리스트 뷰 조립 — plan §"watchlist/service.py"·Phase 2.

모듈 2(stock.summary)의 regime_gate 를 **그대로 소비**해 "신규 진입" 신호를 만든다
(regime-agnostic — 국면명 하드코딩 없이 엔진이 계산한 single_cap/entry_blocked 를 소비만).
종목별 시세는 inquire_price 병렬 조회(캐시 없음, 원칙1). 한 종목 시세 실패가 전체를
죽이지 않는다(번들 철학: 값 None + partial_failure 보존, api/detail.py 동일).

## per-item 계약(프론트 소비)
{...저장필드(ticker, stock_name, reason, target_price, added_at, user_id),
 current_price, change_rate, per, pbr,
 distance_to_target, target_status ∈ {reached, near, far, none},
 entry_signal: {entry_blocked, per_over, pbr_over, single_cap, entry_allowed, note} | None}

## regime 블록
judgement 있으면 {regime, single_cap, entry_blocked}(대표값), 없으면 None + partial_failure "regime".
"""
from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor

from collectors.kis import chart, inquire_price
from stock.summary import regime_entry_blocked, regime_gate
from watchlist.constants import (
    NEAR_TARGET_THRESHOLD_PCT,
    WATCHLIST_FETCH_CONCURRENCY,
    WATCHLIST_SPARK_LOOKBACK_DAYS,
    WATCHLIST_SPARK_POINTS,
)
from watchlist.models import WatchlistItem

_FETCH_TIMEOUT = 15
# 일봉은 수정주가(액면분할 인위 갭 제거 → 스파크라인 추세 연속성). api/detail 일봉과 동일.
_SPARK_ADJ_PRICE = "0"


# ── 목표가 상태 ──────────────────────────────────────────────────────────────

def _distance_to_target(current, target):
    """(current-target)/target*100 (%). target 없음/≤0/현재가 결측 → None."""
    if current is None or target is None or target <= 0:
        return None
    return (current - target) / target * 100.0


def _target_status(current, target, threshold_pct: float) -> str:
    """매수 진입 관점: 목표가는 '사고 싶은 가격'. 현재가가 내려와 목표가에 근접·도달할수록 신호.

    - none:   target 없음/≤0(또는 현재가 결측) — _distance_to_target·프론트와 동일 가드(IMP-01)
    - reached: current <= target(목표가 이하로 도달)
    - near:    current <= target*(1+threshold%)(목표가보다 threshold% 이내로 근접)
    - far:     그 외(아직 멀다)
    """
    if target is None or target <= 0 or current is None:
        return "none"
    if current <= target:
        return "reached"
    if current <= target * (1.0 + threshold_pct / 100.0):
        return "near"
    return "far"


# ── 진입신호(regime_gate 파생) ───────────────────────────────────────────────

def _entry_signal(valuation, judgement):
    """regime_gate 결과 → entry_signal. judgement 없으면 None(진입 판정 불가).

    entry_allowed = 차단 안 됐고 PER/PBR 상한도 안 넘음. entry_blocked·per_over·pbr_over 는
    엔진(regime_gate)이 확정 — 여기서 국면명으로 재판정하지 않는다(single_cap 소비만).
    """
    if judgement is None:
        return None
    gate = regime_gate(valuation, judgement)
    return {
        "entry_blocked": gate["entry_blocked"],
        "per_over": gate["per_over"],
        "pbr_over": gate["pbr_over"],
        "single_cap": gate["single_cap"],
        "entry_allowed": (
            not gate["entry_blocked"] and not gate["per_over"] and not gate["pbr_over"]
        ),
        "note": gate["note"],
    }


# ── per-item enrich ──────────────────────────────────────────────────────────

def _enrich_item(item: WatchlistItem, valuation, judgement, spark) -> dict:
    """저장 필드 + 라이브 시세 + 목표가 상태 + 진입신호 + 스파크라인. valuation None(시세 실패)이면 값 None."""
    valuation = valuation or {}
    current = valuation.get("price")
    target = item.target_price
    return {
        "user_id": item.user_id,
        "ticker": item.ticker,
        "stock_name": item.stock_name,
        "reason": item.reason,
        "target_price": target,
        "added_at": item.added_at,
        "current_price": current,
        "change_rate": valuation.get("change_rate"),
        "per": valuation.get("per"),
        "pbr": valuation.get("pbr"),
        "distance_to_target": _distance_to_target(current, target),
        "target_status": _target_status(current, target, NEAR_TARGET_THRESHOLD_PCT),
        # 시세 실패(valuation 없음)면 게이트 불가 → entry_signal None.
        "entry_signal": _entry_signal(valuation, judgement) if valuation else None,
        # 스파크라인 종가 시계열(선택적) — 시세와 독립 조회, 실패·부재는 None.
        "spark": spark,
    }


def _worker_count(n_tickers: int) -> int:
    """병렬 시세 조회 워커 수 — 종목 수와 상한(WATCHLIST_FETCH_CONCURRENCY) 중 작은 값(≥1).

    종목 수만큼 동시 폭주(최대 30 + 팝업/패널 이중 마운트 + 60s refresh)를 막는 레이트리밋 보호(IMP-09).
    """
    return max(1, min(n_tickers, WATCHLIST_FETCH_CONCURRENCY))


def _fetch_prices_parallel(kis_client, tickers: list[str]) -> tuple[dict, list[str]]:
    """종목별 inquire_price 병렬(ThreadPool, api/detail 패턴). 실패는 partial_failure 로 표면화."""
    valuations: dict = {}
    partial_failure: list[str] = []
    if not tickers:
        return valuations, partial_failure
    with ThreadPoolExecutor(max_workers=_worker_count(len(tickers))) as ex:
        futures = {t: ex.submit(inquire_price.inquire_price, kis_client, t) for t in tickers}
        for ticker, fut in futures.items():
            try:
                valuations[ticker] = fut.result(timeout=_FETCH_TIMEOUT)
            except Exception:
                valuations[ticker] = None
                partial_failure.append(ticker)
    return valuations, partial_failure


# ── 스파크라인(미니차트 종가 시계열) ─────────────────────────────────────────

def _spark_from_chart(chart_result) -> list[float] | None:
    """일봉 candles → date 오름차순 종가 최근 N개(number[]). 비거나 전량 결측이면 None.

    KIS 가 최신순으로 줄 수 있어 date 오름차순 정렬(추세 뒤집힘 방지). 종가 결측 candle 은
    제외(None 이 섞이면 프론트 스케일 계산이 깨진다). 스파크라인은 선택적 시각화라
    실패·부재는 None(빈 리스트 아님 — 프론트 렌더 분기 단순화).
    """
    candles = (chart_result or {}).get("candles") or []
    rows = [(c.get("date"), c.get("close")) for c in candles]
    rows = [(d, v) for (d, v) in rows if d is not None and v is not None]
    rows.sort(key=lambda x: x[0])  # date 오름차순
    closes = [float(v) for (_, v) in rows]
    if not closes:
        return None
    return closes[-WATCHLIST_SPARK_POINTS:]  # 최근 N개(가장 최신이 끝)


def _fetch_one_spark(kis_client, ticker: str) -> list[float] | None:
    """종목 1개 일봉 조회 → 스파크라인. 실패는 None(per-item graceful — 전체 안 죽임)."""
    today = dt.date.today()
    start = (today - dt.timedelta(days=WATCHLIST_SPARK_LOOKBACK_DAYS)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    try:
        # 현재가 캐시 신설 금지(원칙1) — 요청 시점 라이브 조회(캐시 배선 없음).
        result = chart.inquire_daily_itemchartprice(
            kis_client, ticker, start, end, period="D", adj_price=_SPARK_ADJ_PRICE,
        )
        return _spark_from_chart(result)
    except Exception:
        return None  # 스파크라인은 선택적 — 실패는 조용히 None(partial_failure 미오염)


def _fetch_sparks_parallel(kis_client, tickers: list[str]) -> dict:
    """종목별 일봉 병렬 → {ticker: spark|None}. 시세 병렬과 동형(동시성 상한 공유)."""
    sparks: dict = {}
    if not tickers:
        return sparks
    with ThreadPoolExecutor(max_workers=_worker_count(len(tickers))) as ex:
        futures = {t: ex.submit(_fetch_one_spark, kis_client, t) for t in tickers}
        for ticker, fut in futures.items():
            try:
                sparks[ticker] = fut.result(timeout=_FETCH_TIMEOUT)
            except Exception:
                sparks[ticker] = None
    return sparks


# ── 오케스트레이터 ───────────────────────────────────────────────────────────

def build_watchlist_view(store, user_id: str, kis_client, judgement) -> dict:
    """워치리스트 enriched 뷰(등록순). 항상 dict — 라우트는 200(부분실패는 리스트로)."""
    items = store.list_items(user_id)  # added_at 오름차순(registered)
    tickers = [it.ticker for it in items]
    valuations, partial_failure = _fetch_prices_parallel(kis_client, tickers)
    # 스파크라인 일봉은 시세와 독립 병렬(실패는 spark=None, partial_failure 미오염).
    sparks = _fetch_sparks_parallel(kis_client, tickers)

    enriched = [
        _enrich_item(it, valuations.get(it.ticker), judgement, sparks.get(it.ticker))
        for it in items
    ]

    if judgement is None:
        regime_block = None
        if "regime" not in partial_failure:
            partial_failure.append("regime")
    else:
        params = judgement.get("params") or {}
        regime_block = {
            "regime": judgement.get("regime"),
            "single_cap": params.get("single_cap"),
            # 진입차단은 regime_gate 와 같은 헬퍼(단일 출처) — 인라인 재계산 금지(IMP-15).
            "entry_blocked": regime_entry_blocked(params),
        }

    return {
        "items": enriched,
        "regime": regime_block,
        "partial_failure": partial_failure,
    }
