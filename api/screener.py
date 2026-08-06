"""대순환 후보 종목 스크리너 라우트 — GET /api/screener.

두 서빙 경로:
- **scope=cached(기본)**: 배치 스캐너(`stock/screener_scan.py`)가 매일 저장한 **한국시장 전체 보통주**
  스캔 결과(`ScreenerResultStore`)를 **시총 역순 정렬** → stage 필터 → **표시 top-N** 만 라이브 시세
  (가격·등락·현재 PER) enrich + **재무 100점** 산출해 반환. DB 가 비어 있으면(첫 스캔 전) live 폴백.
- **scope=live**: 시총상위 top-N 을 요청 시 라이브 스캔(빠른 조회, 하위호환).

값의 성격 분리(무캐시 원칙1): stage/band·market_cap(정렬키)·재무3축·avg_per·spark 는 스캔 확정/파생
스냅샷(DB) / **가격·현재 PER 은 표시 top-N 만 매 요청 라이브 조회**(저장 금지). 재무 100점 = 스캔
저장 3축(수익성·성장성·안정성) + 서빙 라이브 밸류 축(현재 PER vs 저장 avg_per) → 가용 축 재정규화.

조회 전용(매매 없음)·판정=코드(LLM 0)·market/scope 화이트리스트 폴백·size clamp·KIS 실패 **항상 200
graceful**. 단계 필터는 이제 **서버 파라미터**(?stage=) — 표시 top-N 선정에 필요(정렬 후 상위만 enrich).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.detail import _resolve_client  # KIS 클라이언트 해석(본인/공유/env·null 흡수) SSOT
from auth.deps import get_current_user_optional
from auth.models import User
from collectors.kis import inquire_price
from collectors.kis.ranking import MARKET_ISCD
from infra.db import get_db
from infra.parallel import fetch_parallel
from infra.timeutil import now_iso  # as_of 타임스탬프 — timeutil SSOT(인라인 datetime 조립 제거)
from stock.constants import FINANCIAL_SCORE_CONFIG, INDICATOR_CONFIG
from stock.financial_score import financial_score
from stock.screener import screen_grand_cycle
from stock.screener_store import default_store
from watchlist.constants import WATCHLIST_FETCH_CONCURRENCY

router = APIRouter()

_SIZE_MIN, _SIZE_MAX, _SIZE_DEFAULT = 10, 40, 30
_SCOPES = {"cached", "live"}
# 사용자 market → 저장 행의 market 값. all/kospi200 은 행 필터 없음(kospi200 은 cached 미지원 → live 폴백).
_ROW_MARKET = {"kospi": "KOSPI", "kosdaq": "KOSDAQ"}
_RISING_STAGES = (1, 6)  # 상승 국면(안정 상승기·상승 진입기) — stage="rising" 필터
_DISPLAY_LIMIT = 60      # 시총 상위 표시·라이브 enrich 대상 수(패널 표시 상한)
_ENRICH_TIMEOUT = 20.0   # 표시 top-N 라이브 시세 병렬 상한(초)


def _get_store():
    """스캔 결과 스토어(테스트 monkeypatch 경계). 앱 기본 세션팩토리 싱글턴."""
    return default_store()


def _live_price(client, ticker: str) -> dict:
    """단일 종목 라이브 시세(price/change_rate/현재 PER). enrich·테스트 경계(무캐시 원칙1)."""
    return inquire_price.inquire_price(client, ticker)


def _stage_filtered(candidates: list[dict], stage) -> list[dict]:
    """stage 필터: None/"all"=전부, "rising"=상승국면(1·6), "1".."6"=해당 단계. 불량=전부."""
    if stage in (None, "all"):
        return list(candidates)
    if stage == "rising":
        return [c for c in candidates if c.get("stage") in _RISING_STAGES]
    try:
        s = int(stage)
    except (TypeError, ValueError):
        return list(candidates)
    return [c for c in candidates if c.get("stage") == s]


def _by_market_cap_desc(candidates: list[dict]) -> list[dict]:
    """시가총액 역순 정렬. market_cap 결측(None)은 맨 뒤로(정렬 근거 없는 후보 하위)."""
    return sorted(
        candidates,
        key=lambda c: (c.get("market_cap") is not None, c.get("market_cap") or 0.0),
        reverse=True,
    )


def _attach_score(c: dict) -> None:
    """후보에 재무 100점 부여(판정=코드). 밸류 축은 라이브 PER vs 저장 avg_per(없으면 3축 재정규화).

    per_vs_avg = (현재 PER − avg_per)/avg_per×100. 둘 중 하나라도 결측이면 밸류 축 제외.
    """
    live_per = c.get("per")
    avg = c.get("avg_per")
    per_vs_avg = None
    if live_per is not None and avg not in (None, 0):
        per_vs_avg = (live_per - avg) / avg * 100.0
    # 스캔 저장 3축 원천으로 단일 연간 행 재구성 → financial_score(SSOT 점수 엔진).
    ratio = [{
        "roe": c.get("roe"),
        "net_income_growth": c.get("net_income_growth"),
        "debt_ratio": c.get("debt_ratio"),
    }]
    fs = financial_score(ratio, per_vs_avg=per_vs_avg)
    c["fin_score"] = fs["score"]
    c["fin_axes"] = fs["axes"]
    c["per_vs_avg"] = per_vs_avg


def _enrich_and_score(client, candidates: list[dict]) -> list[str]:
    """표시 top-N 라이브 시세(가격·등락·현재 PER) 병렬 조회 후 재무 100점 부여. partial_failure 반환.

    client 없음(자격증명 미보유)이면 시세 없이 재무 3축 점수만(graceful). 시세 실패 종목은
    price/per None + partial_failure(선택적 — 화면은 stage/재무점수/스파크로 여전히 유용).
    """
    failed: list[str] = []
    prices: dict = {}
    if client is not None and candidates:
        jobs = {
            c["ticker"]: (lambda t=c["ticker"]: _live_price(client, t))
            for c in candidates if c.get("ticker")
        }
        workers = max(1, min(len(jobs), WATCHLIST_FETCH_CONCURRENCY))
        prices, failed = fetch_parallel(jobs, max_workers=workers, timeout=_ENRICH_TIMEOUT)
    for c in candidates:
        val = prices.get(c.get("ticker")) or {}
        c["price"] = val.get("price")
        c["change_rate"] = val.get("change_rate")
        c["per"] = val.get("per")  # 현재(후행) PER — 라이브(무캐시 원칙1)
        _attach_score(c)
    return failed


def _cached_result(client, market: str, iscd: str, stage) -> dict | None:
    """DB 최신 스캔 → 시총 정렬 → stage 필터 → 표시 top-N enrich+점수. DB 비면/kospi200 → None(live 폴백).

    candidates = **표시 top-N**(시총 상위·enrich 완료). total = stage 필터 후 후보 수(top-N 이전),
    universe_size = 스캔 대상 수(stage None 포함). 프론트는 candidates 를 그대로 그리고 "외 (total−N)".
    """
    if market == "kospi200":
        return None  # 마스터에 편입정보 없음 → cached 재현 불가(live 폴백)
    store = _get_store()
    as_of = store.latest_as_of()
    if as_of is None:
        return None  # 첫 스캔 전 → live 폴백
    rows = store.list_results(as_of_date=as_of, market=_ROW_MARKET.get(market))
    classified = [r for r in rows if r.get("stage") is not None]
    filtered = _stage_filtered(classified, stage)
    ranked = _by_market_cap_desc(filtered)
    top = ranked[:_DISPLAY_LIMIT]
    failed = _enrich_and_score(client, top)
    return {
        "candidates": top,                              # 표시 top-N(시총 상위·enrich)
        "catalog": INDICATOR_CONFIG.get("grand_cycle"),  # 6단계 라벨 SSOT → 프론트 전파
        "score_config": FINANCIAL_SCORE_CONFIG,          # 재무점수 축 라벨 SSOT → 프론트 전파
        "market": market,
        "market_iscd": iscd,
        "scope": "cached",
        "as_of": as_of,               # 스캔일 "YYYY-MM-DD"
        "stage": stage or "all",
        "total": len(filtered),       # stage 필터 후 후보 수(표시 상한 이전)
        "displayed": len(top),
        "universe_size": len(rows),   # 스캔 대상 수(None 포함)
        "partial_failure": failed,
    }


def _live_result(client, market: str, iscd: str, size: int, stage) -> dict:
    """시총상위 top-N 라이브 스캔(폴백). KIS 실패는 항상 graceful(빈 후보 + partial_failure).

    live 후보는 ranking 에서 price/change/market_cap 을 이미 갖는다(별도 시세 enrich 안 함) —
    재무 3축·avg_per 는 없어 fin_score=None(첫 스캔 전 임시). stage 필터·시총 정렬은 동일 적용.
    """
    try:
        result = screen_grand_cycle(client, market_iscd=iscd, size=size)
        result["market"] = market
        result["scope"] = "live"
        cands = _by_market_cap_desc(_stage_filtered(result.get("candidates") or [], stage))
        for c in cands:
            _attach_score(c)  # 시세 enrich 없이 점수 shape 통일(재무 없음 → fin_score None)
        result["candidates"] = cands
        result["stage"] = stage or "all"
        result["total"] = len(cands)
        result["displayed"] = len(cands)
        result["universe_size"] = len(cands)
        result["score_config"] = FINANCIAL_SCORE_CONFIG
        return result
    except Exception:  # noqa: BLE001 — KIS/자격증명 실패는 graceful(빈 후보 + partial_failure)
        return {
            "candidates": [], "catalog": None, "score_config": FINANCIAL_SCORE_CONFIG,
            "market": market, "market_iscd": iscd, "scope": "live", "size": size,
            "stage": stage or "all", "total": 0, "displayed": 0, "universe_size": 0,
            "partial_failure": ["screener"], "as_of": now_iso(),
        }


@router.get("/api/screener")
def screener(
    market: str = "all",
    size: int = _SIZE_DEFAULT,
    scope: str = "cached",
    stage: str = "all",
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> dict:
    """대순환 단계 후보 스크리너(시총 역순 정렬 + 표시 top-N 라이브 가격/PER + 재무 100점).

    market: all/kospi/kosdaq/kospi200(화이트리스트 폴백 all) · size: 10~40 clamp(live 전용) ·
    scope: cached(기본, 전체 유니버스 DB)/live(top-N 라이브) · stage: all/rising/1..6(표시 후보 필터).
    cached 인데 DB 비었으면 live 폴백. `_resolve_client` 로 client 확보(cached enrich·live 공용·옵션
    인증). KIS 실패는 항상 200(빈 후보 또는 시세 결측 graceful).
    """
    market = market if market in MARKET_ISCD else "all"
    iscd = MARKET_ISCD[market]
    size = max(_SIZE_MIN, min(size, _SIZE_MAX))
    scope = scope if scope in _SCOPES else "cached"
    client = _resolve_client(user, db)  # cached 표시 enrich + live 둘 다 client 필요

    if scope == "cached":
        cached = _cached_result(client, market, iscd, stage)
        if cached is not None:
            return cached
        # DB 비었거나 kospi200(미지원) → live 폴백(화면이 빈손 아니게)

    return _live_result(client, market, iscd, size, stage)
