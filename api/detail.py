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
- 조회 전용(order/buy/sell 없음). 번들은 국면정합성 게이트(regime_gate)를 폐기(항목3) —
  국면과 무관하다. judgement 파라미터는 report.py 호환용으로만 유지(번들 내부 미사용).
"""
from __future__ import annotations

import datetime as dt
from infra.parallel import fetch_parallel

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import assert_valid_ticker  # {ticker} 라우트 진입부 400 차단(공용)
from api.deps import build_judgement as _build_judgement  # 국면 판정 빌더 SSOT(IMP-06)
from auth.deps import get_current_user_optional
from auth.models import User
from infra.db import get_db
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
from infra.config import KisConfig, kis_account
from stock.constants import INDICATOR_CONFIG, STOCK_META_TTL_SECONDS
from stock.summary import build_stock_summary, forward_valuation, stage_segments_for_chart

router = APIRouter()

_FETCH_TIMEOUT = 15
_CHART_LOOKBACK_DAYS = 190  # ~6개월 일봉(기술적 지표 창·번들 요약용)
# 선택형 차트 기간(일수) — 사용자 선택 3개월/1년/3년/10년. KIS ~100/콜이라 장기간은 페이지네이션.
_CHART_RANGE_DAYS = {"3m": 92, "1y": 366, "3y": 1096, "10y": 3653}
_CHART_PERIODS = {"D", "W"}  # 일봉/주봉(월/년은 현재 미노출)
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
    # 실패 key 는 partial_failure(섹션별 graceful null) — 공용 fetch_parallel 로 통합.
    return fetch_parallel(fetchers, max_workers=len(fetchers), timeout=_FETCH_TIMEOUT)


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

    # 국면정합성 게이트(regime_gate)는 폐기(항목3) — 번들은 국면 커트를 판정하지 않는다(현금비중은
    # 매크로 대시보드가 별도 표시). judgement 는 시그니처 유지용(미사용).

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
        "forward_valuation": forward_val,
        "indicator_config": dict(INDICATOR_CONFIG),  # SSOT → 프론트 차트 지표 기간
        "partial_failure": partial_failure,
    }


# ── 라우트 배선 ──────────────────────────────────────────────────────────────

class NoKisCredentials(Exception):
    """유저 등록키·공유 fallback·env 어디에도 KIS 자격증명이 없을 때(라우트가 graceful 처리)."""


class ResolvedKis:
    """해석된 KIS 접근 — 클라이언트 + 계좌(cano/prdt) + 출처(user|shared|env)."""

    __slots__ = ("client", "cano", "prdt", "source")

    def __init__(self, client, cano: str, prdt: str, source: str) -> None:
        self.client = client
        self.cano = cano
        self.prdt = prdt
        self.source = source


def _build_kis_client_from(app_key: str, app_secret: str, env: str):
    """주어진 자격증명으로 KIS 클라이언트 조립(토큰 provider). 토큰 캐시는 app_key 별 격리."""
    from cache.local import FileCache
    from collectors.kis import auth
    from collectors.kis.client import KisClient

    config = KisConfig(app_key=app_key, app_secret=app_secret, env=env, account_no="")
    provider = auth.make_token_provider(config, FileCache(_TOKEN_CACHE_PATH))
    return KisClient(config, provider)


def _build_kis_client():
    """env(.env) 기반 조립 — 하위호환·테스트 monkeypatch 경계. 진입점은 resolve_kis_client."""
    config = KisConfig.load()
    return _build_kis_client_from(config.app_key, config.app_secret, config.env)


def resolve_kis_client(user, db) -> ResolvedKis:
    """KIS 자격증명 해석: 본인 등록키 → 공유(__shared__) → env(.env, 로컬) 순.

    - user(Optional[User])·db(Optional[Session]). 로그인+등록 시 본인 키, 아니면 공유 fallback,
      그것도 없으면 로컬 .env, 다 없으면 NoKisCredentials(라우트가 graceful).
    - 반환 ResolvedKis(client, cano, prdt, source). 시크릿은 여기서만 in-memory 복호화.
    """
    user_id = str(user.id) if user is not None else None
    if db is not None:
        from auth.kis_store import KisCredentialStore

        resolved = KisCredentialStore(db).resolve(user_id)
        if resolved is not None:
            creds, source = resolved
            client = _build_kis_client_from(creds.app_key, creds.app_secret, creds.env)
            return ResolvedKis(client, creds.account_no, creds.acnt_prdt_cd, source)
    try:  # env fallback(로컬 개발 .env)
        config = KisConfig.load()
    except Exception as exc:
        raise NoKisCredentials() from exc
    cano, prdt = kis_account()
    client = _build_kis_client_from(config.app_key, config.app_secret, config.env)
    return ResolvedKis(client, cano, prdt, "env")


class _NullKisClient:
    """자격증명 부재 시 자리표시자 — 모든 조회가 실패해 KIS 섹션이 graceful null 이 된다."""

    env = "real"

    def get(self, *args, **kwargs):  # noqa: D401
        raise NoKisCredentials("KIS 자격증명 없음")


def _resolve_client(user, db):
    """시장데이터 라우트용 KIS 클라이언트 해석(본인/공유/env). 자격증명 없으면 null client.

    **테스트 monkeypatch 경계** — 종목번들·리포트·워치리스트·view_context 가 이 함수로 클라이언트를
    얻는다(각 소비 모듈이 이 이름을 바인딩). NoKisCredentials 는 null client 로 흡수 → 섹션 graceful null.
    """
    try:
        return resolve_kis_client(user, db).client
    except NoKisCredentials:
        return _NullKisClient()


@router.get("/api/detail/{ticker}/bundle")
def stock_detail_bundle(
    ticker: str,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> dict:
    """종목 종합리포트 번들(§6.5). 번들은 국면과 무관(regime_gate 폐기, 항목3) — 종목 섹션만.

    공개 유지(옵션 인증) — 로그인+등록 시 본인 KIS 키, 아니면 공유 fallback. 자격증명 없으면
    KIS 섹션 graceful null(항상 200).
    """
    # 번들은 judgement 를 소비하지 않는다(regime_gate 폐기) — 낭비 FRED 호출 없이 None 전달.
    client = _resolve_client(user, db)
    return collect_stock_bundle(ticker, client, None, cache=_META_CACHE)


@router.get("/api/detail/{ticker}/chart")
def stock_detail_chart(
    ticker: str,
    period: str = "D",
    range: str = "1y",  # noqa: A002 — 쿼리 키(?range=)로 노출. 함수 내 builtin range() 미사용.
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> dict:
    """선택형 차트 — **일봉/주봉 × 3개월/1년/3년/10년**. KIS ~100/콜 상한을 페이지네이션으로 넘는다.

    스테이지 리본(`stage_segments`)은 **표시 시계열로 재계산**(대순환은 각 timeframe 유효). **정량 요약
    (RSI/MA/현재 대순환 단계)은 번들[일봉]에 pin** — 여기선 표시 데이터만. **일봉 무캐시**(오늘봉 형성,
    원칙1). 불량 ticker 400, KIS 실패는 **항상 200 graceful**(빈 candles + partial_failure).
    """
    assert_valid_ticker(ticker)
    period = period if period in _CHART_PERIODS else "D"
    range_key = range if range in _CHART_RANGE_DAYS else "1y"
    lookback = _CHART_RANGE_DAYS[range_key]
    client = _resolve_client(user, db)
    try:
        raw = chart.fetch_chart_series(
            client, ticker, period=period,
            start_date=_days_ago(lookback), end_date=_today(),
            adj_price=_DAILY_ADJ_PRICE,
        )
        candles = raw.get("candles") or []
        seg = stage_segments_for_chart({"candles": candles})  # 표시 차트로 리본 재계산
        return {
            "ticker": ticker, "period": period, "range": range_key,
            "candles": candles,
            "stage_segments": seg["stage_segments"],
            "current_stage": seg["current_stage"],
            "partial_failure": [],
        }
    except Exception:  # noqa: BLE001 — KIS/자격증명 실패는 삼키지 않되 graceful(빈 차트)
        return {
            "ticker": ticker, "period": period, "range": range_key,
            "candles": [], "stage_segments": [], "current_stage": None,
            "partial_failure": ["chart"],
        }
