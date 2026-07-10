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

from concurrent.futures import ThreadPoolExecutor

from collectors.kis import inquire_price
from stock.summary import regime_entry_blocked, regime_gate
from watchlist.constants import NEAR_TARGET_THRESHOLD_PCT, WATCHLIST_FETCH_CONCURRENCY
from watchlist.models import WatchlistItem

_FETCH_TIMEOUT = 15


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

def _enrich_item(item: WatchlistItem, valuation, judgement) -> dict:
    """저장 필드 + 라이브 시세 + 목표가 상태 + 진입신호. valuation None(시세 실패)이면 값 None."""
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


# ── 오케스트레이터 ───────────────────────────────────────────────────────────

def build_watchlist_view(store, user_id: str, kis_client, judgement) -> dict:
    """워치리스트 enriched 뷰(등록순). 항상 dict — 라우트는 200(부분실패는 리스트로)."""
    items = store.list_items(user_id)  # added_at 오름차순(registered)
    tickers = [it.ticker for it in items]
    valuations, partial_failure = _fetch_prices_parallel(kis_client, tickers)

    enriched = [_enrich_item(it, valuations.get(it.ticker), judgement) for it in items]

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
