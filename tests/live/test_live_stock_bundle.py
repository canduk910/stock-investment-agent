"""W08 종목 번들 라이브 검증 게이트 — plan '남은 라이브 확인' 4항목.

실 KIS 키(real 권장)로만 도는 게이트. @pytest.mark.live 로 분리돼 기본 실행
(-m 'not live')에서 제외되므로 키 없는 CI/QA 도 green. 실행: `uv run pytest -m live`.

각 테스트는 계획의 미검증 가정을 실응답으로 좁힌다:
  1. 재무 API 히스토리 연수 ≥ MIN_HISTORY_YEARS (CAGR/avg_per 표본 확보)
  2. avg_per 근사의 EPS/주가 조정기준 일치(액면분할) — PER_year 가 현재 PER 과
     같은 스케일인지(불일치 시 valuation_label 오염 → AVG_PER_VERIFIED 유지 False)
  3. 재무 API 모의(demo) 도메인 지원 여부 — 다수 재무 TR 이 real 전용
  4. 일봉 회당 행 상한 — 6개월 창 단일호출 가능 여부
"""
from __future__ import annotations

import pytest

from collectors.kis import (
    finance_financial_ratio,
    finance_income_statement,
    inquire_price,
)
from collectors.kis.errors import KisApiError
from infra.config import ConfigError, KisConfig
from stock.constants import MIN_HISTORY_YEARS

pytestmark = pytest.mark.live

TICKER = "005930"  # 삼성전자 (2018년 50:1 액면분할 — 조정기준 검증에 적합)


def _kis_client():
    from cache.local import FileCache
    from collectors.kis import auth
    from collectors.kis.client import KisClient

    config = KisConfig.load()
    cache = FileCache(".cache/kis_token.json")
    provider = auth.make_token_provider(config, cache)
    return KisClient(config, provider), config


def _client_or_skip():
    try:
        return _kis_client()
    except ConfigError as exc:
        pytest.skip(f"KIS 키 없음: {exc}")


# 1. 재무 히스토리 연수 ──────────────────────────────────────────────────────

def test_live_financials_history_years():
    """income/ratio 가 MIN_HISTORY_YEARS 이상 연도를 주는지(표본 왜곡 게이트)."""
    client, _ = _client_or_skip()

    income = finance_income_statement.finance_income_statement(client, TICKER)
    ratio = finance_financial_ratio.finance_financial_ratio(client, TICKER)
    income_years = {r["period"][:4] for r in income if r.get("period")}
    ratio_years = {r["period"][:4] for r in ratio if r.get("period")}
    print(f"\n[live] income years={sorted(income_years)} ratio years={sorted(ratio_years)}")

    assert len(income_years) >= MIN_HISTORY_YEARS, (
        f"손익계산서 연수 {len(income_years)} < {MIN_HISTORY_YEARS} — CAGR/avg_per 표본 부족, "
        "DART 보강을 W09 P2 로 검토"
    )
    assert len(ratio_years) >= MIN_HISTORY_YEARS


# 2. avg_per EPS/주가 조정기준 일치 ──────────────────────────────────────────

def test_live_avg_per_adjustment_basis_consistency():
    """연도별 EPS × 결산기말 종가로 만든 PER 이 현재 PER 과 같은 스케일인가.

    액면분할 종목에서 EPS(재무·분할 미반영일 수 있음)와 종가(원주가)의 조정기준이
    어긋나면 PER_year 가 현재 PER 대비 자릿수로 튄다. 그 경우 AVG_PER_VERIFIED 를
    True 로 올리면 안 된다. 여기서는 최근 연도 PER_year 가 현재 PER 의 0.2~5배
    범위인지 소프트 확인(범위 밖이면 조정기준 불일치 의심 → 실패로 표면화)."""
    from api import detail

    client, _ = _client_or_skip()

    ratio = finance_financial_ratio.finance_financial_ratio(client, TICKER)
    year_end = detail._fetch_year_end_prices(client, TICKER, {"ratio": ratio, "income": []})
    valuation = inquire_price.inquire_price(client, TICKER)
    current_per = valuation.get("per")

    pers = {}
    for row in ratio:
        period, eps = row.get("period"), row.get("eps")
        close = year_end.get(period)
        if eps and eps > 0 and close and close > 0:
            pers[period] = round(close / eps, 2)
    print(f"\n[live] current_per={current_per} PER_year={pers}")

    assert pers, "결산기말 종가/EPS 매칭 0건 — 월봉 date[:6] 매칭 또는 연도 커버리지 확인"
    assert current_per and current_per > 0
    recent = pers[max(pers)]
    ratio_to_current = recent / current_per
    assert 0.2 <= ratio_to_current <= 5.0, (
        f"최근 PER_year {recent} 가 현재 PER {current_per} 대비 {ratio_to_current:.1f}배 — "
        "EPS/주가 조정기준(액면분할) 불일치 의심. AVG_PER_VERIFIED 를 True 로 올리지 말 것"
    )


# 3. 재무 API 모의 도메인 지원 여부 ─────────────────────────────────────────

def test_live_financials_demo_domain_support():
    """설정된 env 에서 재무 TR 이 동작하는지. demo 미지원이면 KisApiError → 문서화 skip."""
    client, config = _client_or_skip()

    try:
        income = finance_income_statement.finance_income_statement(client, TICKER)
    except KisApiError as exc:
        if config.env == "demo":
            pytest.skip(
                f"재무 API 모의(demo) 미지원 확인 — 데모 환경에서 financials degraded 는 "
                f"의도된 동작(real 키 필요). msg={exc}"
            )
        raise
    assert isinstance(income, list) and income, f"env={config.env} 재무 응답 비어있음"


# 4. 일봉 회당 행 상한 ───────────────────────────────────────────────────────

def test_live_daily_chart_row_cap():
    """6개월 일봉 단일 호출이 창을 다 채우는지(회당 행 상한 확인)."""
    from api import detail

    client, _ = _client_or_skip()

    result = detail._fetch_chart(client, TICKER)
    n = len(result.get("candles") or [])
    print(f"\n[live] 6mo daily candles={n}")

    assert n > 0, "일봉 0건 — 조회 파라미터/기간 확인"
    # ~6개월(약 120 거래일) 창. 회당 상한(예: 100)에 걸리면 창 축소/페이지네이션(P2) 필요.
    if n < 100:
        print(f"[live] 경고: 6개월 창 캔들 {n} < 100 — 회당 상한 또는 기간 부족 가능")
