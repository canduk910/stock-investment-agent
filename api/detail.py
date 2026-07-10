"""종목 종합리포트 번들 오케스트레이터 + 라우트 — plan §5.1·§6.5.

`GET /api/detail/{ticker}/bundle` 하나로 팝업/페이지에 필요한 데이터를 전부 반환한다
(N+1 방지). 매크로 대시보드(macro_snapshot)와 동일 철학: 병렬 수집 + partial_failure
보존, 판정·계산은 코드(순수 엔진 stock.summary), LLM 미개입.

## 2단계 수집
1차(병렬, ThreadPool): basic(메타)·valuation(라이브)·financials(income+ratio)·chart(일봉).
2차(순차): financials 성공 시 결산기말 종가를 **월봉 단일 호출**로 받아
year_end_prices={period: close} 조립(avg_per 재료). 월봉 실패는 년말가만 비고 섹션은 유지.

## 캐시 3원칙 (구조적 강제)
- 원칙1: valuation·chart 는 저장하지 않는다(어댑터에 cache 인자 없음 + 여기서도 미저장).
- 원칙2 명시 게이트: 섹션 dict 엔 partial_failure 키가 없어 cache_if_clean 만으로는
  무력하다 → 'financials' 가 번들 partial_failure 에 **없을 때만** financials·basic 메타를
  저장한다. degraded(빈 output 승격)도 저장 안 함.

## 안전
- 조회 전용(order/buy/sell 없음). regime_gate 는 매크로 국면 파라미터를 소비만 한다.
- 매크로 수집 실패 → regime_gate=None + partial_failure 에 'regime'(항상 200).
"""
from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter

from api.deps import build_judgement as _build_judgement  # 국면 판정 빌더 SSOT(IMP-06)
from cache.keys import stock_meta_sub_key
from cache.local import LocalCache
from cache.policy import cache_if_clean
from collectors.kis import (
    chart,
    estimate_perform,
    finance_financial_ratio,
    finance_income_statement,
    inquire_price,
    stock_info,
)
from infra.config import KisConfig
from stock.constants import INDICATOR_CONFIG, STOCK_META_TTL_SECONDS
from stock.summary import build_stock_summary, forward_valuation, regime_gate

router = APIRouter()

_FETCH_TIMEOUT = 15
_CHART_LOOKBACK_DAYS = 190  # ~6개월 일봉(기술적 지표 창)
# 일봉(기술적): 수정주가 — 액면분할이 인위적 갭을 만들지 않게(RSI/MA 연속성).
_DAILY_ADJ_PRICE = "0"
# 월봉(avg_per 결산기말 종가): 원주가 — 재무제표 원본 EPS 와 조정기준 정합.
# ⚠ EPS/주가 조정기준 일치는 라이브 검증 항목(constants.AVG_PER_VERIFIED). 검증 전엔
#   엔진이 avg_per/valuation_label 을 None 폴백하므로 이 값 자체가 라벨을 오염시키진 않는다.
_MONTHLY_ADJ_PRICE = "1"
_TOKEN_CACHE_PATH = ".cache/kis_token.json"

# 로컬 스탠드인용 인메모리 메타 캐시(원칙2 게이트 경유 저장). 배포 시 ElastiCache 로 교체.
_META_CACHE = LocalCache()


# ── 날짜 헬퍼 ────────────────────────────────────────────────────────────────

def _today() -> str:
    return dt.date.today().strftime("%Y%m%d")


def _days_ago(days: int) -> str:
    return (dt.date.today() - dt.timedelta(days=days)).strftime("%Y%m%d")


# ── 섹션 fetch ───────────────────────────────────────────────────────────────

def _fetch_financials(client, ticker: str) -> dict:
    """손익계산서(income) + 재무비율(ratio) 순차 조회 → {income, ratio}.

    둘 중 하나라도 예외면 financials 섹션 실패로 본다(신뢰 불가 → 전체 null).
    """
    income = finance_income_statement.finance_income_statement(client, ticker)
    ratio = finance_financial_ratio.finance_financial_ratio(client, ticker)
    return {"income": income, "ratio": ratio}


def _fetch_chart(client, ticker: str) -> dict:
    """~6개월 일봉(캔들+기술적 지표 겸용). 오늘봉 형성 중이라 캐시 금지."""
    return chart.inquire_daily_itemchartprice(
        client, ticker, _days_ago(_CHART_LOOKBACK_DAYS), _today(),
        period="D", adj_price=_DAILY_ADJ_PRICE,
    )


def _fetch_sections_parallel(client, ticker: str) -> tuple[dict, list[str]]:
    fetchers = {
        "basic": lambda: stock_info.search_stock_info(client, ticker),
        "valuation": lambda: inquire_price.inquire_price(client, ticker),
        "financials": lambda: _fetch_financials(client, ticker),
        "chart": lambda: _fetch_chart(client, ticker),
        "estimate": lambda: estimate_perform.estimate_perform(client, ticker),  # 예측실적(리서치 ~160종목)
    }
    sections: dict = {}
    partial_failure: list[str] = []
    with ThreadPoolExecutor(max_workers=len(fetchers)) as ex:
        futures = {key: ex.submit(fn) for key, fn in fetchers.items()}
        for key, fut in futures.items():
            try:
                sections[key] = fut.result(timeout=_FETCH_TIMEOUT)
            except Exception:
                sections[key] = None
                partial_failure.append(key)
    return sections, partial_failure


# ── 2차: 결산기말 종가(월봉) ─────────────────────────────────────────────────

def _financial_periods(financials: dict) -> set[str]:
    periods: set[str] = set()
    for section in ("income", "ratio"):
        for row in financials.get(section) or []:
            period = row.get("period")
            if period:
                periods.add(str(period))
    return periods


def _fetch_year_end_prices(client, ticker: str, financials: dict) -> dict:
    """결산기말(period=stac_yymm) → 종가. 월봉 단일 호출 후 캔들 date[:6] 로 매칭."""
    periods = _financial_periods(financials)
    years = sorted({p[:4] for p in periods if len(p) >= 4})
    if not years:
        return {}
    monthly = chart.inquire_daily_itemchartprice(
        client, ticker, f"{years[0]}0101", _today(),
        period="M", adj_price=_MONTHLY_ADJ_PRICE,
    )
    month_close: dict = {}
    for candle in monthly.get("candles") or []:
        date = candle.get("date")
        close = candle.get("close")
        if date and len(date) >= 6 and close is not None:
            month_close[date[:6]] = close
    return {period: month_close[period] for period in periods if period in month_close}


def _financials_is_empty(financials: dict) -> bool:
    """income·ratio 핵심값이 전부 None(빈 output 포함) → degraded(신규상장 재무 결측)."""
    income = financials.get("income") or []
    ratio = financials.get("ratio") or []
    income_has = any(
        r.get("revenue") is not None
        or r.get("operating_income") is not None
        or r.get("net_income") is not None
        for r in income
    )
    ratio_has = any(
        r.get("eps") is not None or r.get("bps") is not None or r.get("roe") is not None
        for r in ratio
    )
    return not (income_has or ratio_has)


# ── 캐시 게이트(원칙2 명시) ──────────────────────────────────────────────────

def _cache_meta_sections(cache, ticker: str, sections: dict, partial_failure: list[str]) -> None:
    """'financials' 가 partial_failure 에 없을 때만 financials·basic 메타 저장(degraded 제외)."""
    if cache is None or "financials" in partial_failure:
        return
    financials = sections.get("financials")
    if financials is not None:
        cache_if_clean(cache, stock_meta_sub_key(ticker, "financials"), financials, STOCK_META_TTL_SECONDS)
    basic = sections.get("basic")
    if basic is not None and "basic" not in partial_failure:
        cache_if_clean(cache, stock_meta_sub_key(ticker, "basic"), basic, STOCK_META_TTL_SECONDS)


# ── 오케스트레이터 ───────────────────────────────────────────────────────────

def collect_stock_bundle(ticker: str, kis_client, judgement, cache=None) -> dict:
    """KIS 병렬 조회 → 순수 엔진 조립 → 번들 계약 반환(항상 dict, 라우트는 200)."""
    sections, partial_failure = _fetch_sections_parallel(kis_client, ticker)

    financials = sections.get("financials")
    if financials is not None:
        if _financials_is_empty(financials):
            if "financials" not in partial_failure:
                partial_failure.append("financials")  # degraded 승격
        else:
            try:
                financials["year_end_prices"] = _fetch_year_end_prices(kis_client, ticker, financials)
            except Exception:
                financials["year_end_prices"] = {}  # 월봉 실패는 년말가만 비움(섹션 유지)

    summary = build_stock_summary(
        sections.get("basic"),
        sections.get("financials"),
        sections.get("valuation"),
        sections.get("chart"),
    )

    if judgement is None:
        regime_gate_result = None
        if "regime" not in partial_failure:
            partial_failure.append("regime")
    else:
        regime_gate_result = regime_gate(sections.get("valuation"), judgement)

    # 예측 PER(리서치 컨센서스). estimate 실패는 partial_failure 로 표면화(번들은 죽지 않음).
    if "estimate" in partial_failure:
        forward_val = None
    else:
        forward_val = forward_valuation(sections.get("estimate"), sections.get("valuation"))

    _cache_meta_sections(cache, ticker, sections, partial_failure)

    return {
        "ticker": ticker,
        "basic": sections.get("basic"),
        "valuation": sections.get("valuation"),
        "financials": sections.get("financials"),
        "chart": sections.get("chart"),
        "summary": summary,
        "regime_gate": regime_gate_result,
        "forward_valuation": forward_val,
        "indicator_config": dict(INDICATOR_CONFIG),  # SSOT → 프론트 차트 지표 기간
        "partial_failure": partial_failure,
    }


# ── 라우트 배선 ──────────────────────────────────────────────────────────────

def _build_kis_client():
    """실 KIS 클라이언트 조립(토큰 provider + env). 테스트는 이 함수를 monkeypatch."""
    from cache.local import FileCache
    from collectors.kis import auth
    from collectors.kis.client import KisClient

    config = KisConfig.load()
    token_cache = FileCache(_TOKEN_CACHE_PATH)
    provider = auth.make_token_provider(config, token_cache)
    return KisClient(config, provider)


@router.get("/api/detail/{ticker}/bundle")
def stock_detail_bundle(ticker: str) -> dict:
    """종목 종합리포트 번들(§6.5). 매크로 수집 실패는 regime 만 degraded, 종목은 정상."""
    try:
        judgement = _build_judgement()
    except Exception:
        judgement = None  # regime_gate=None + partial_failure 에 'regime'(collect_stock_bundle 내부)
    client = _build_kis_client()
    return collect_stock_bundle(ticker, client, judgement, cache=_META_CACHE)
