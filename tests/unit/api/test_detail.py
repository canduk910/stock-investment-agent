"""종목 번들 API 계약 테스트 — plan §5.1·§6.5·T8 (번들 오케스트레이터 + 라우트).

collect_stock_bundle 은 KIS 조회 어댑터(client.get 경계)를 병렬 호출해 섹션을 모으고,
순수 엔진(build_stock_summary·regime_gate)으로 정량요약·국면정합성을 조립한다. 여기서는
client.get 을 tr_id 별 fixture 로 라우팅하는 stub 으로 대체(경계 mock)하고, 그 안쪽
조립·partial_failure·캐시 게이트를 실제 코드로 통과시킨다(엔진도 실제 순수함수 사용).

캐시 3원칙 고정:
- 원칙1: valuation(현재가·PER·52주)은 어떤 키로도 저장되지 않는다.
- 원칙2: 'financials' 가 번들 partial_failure 에 있으면(실패·degraded) 메타를 저장하지 않는다.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api.detail as detail
import api.main as main

# 번들 계약 최상위 키(프론트·QA 의존).
BUNDLE_KEYS = {
    "ticker", "basic", "valuation", "financials", "chart",
    "summary", "regime_gate", "forward_valuation", "indicator_config", "partial_failure",
}

# 섹션 → 해당 섹션을 담당하는 KIS TR_ID(주입 실패용).
SECTION_TR = {
    "basic": "CTPF1002R",
    "valuation": "FHKST01010100",
    "financials": "FHKST66430200",  # 손익계산서(income) 실패 → financials 섹션 실패
    "chart": "FHKST03010100",
    "estimate": "HHKST668300C0",  # 종목추정실적 실패 → forward_valuation=None
}

# 종목추정실적 응답(축약) — 행=지표, 열 data1~5=연도(output4). r1=EPS·r3=PER(÷10), 2026E/2027E 추정.
_ESTIMATE_BODY = {
    "rt_cd": "0",
    "output1": {"name1": "홍길동", "estdate": "20260630", "rcmd_name": "매수", "item_kor_nm": "삼성전자"},
    "output2": [
        {"data1": "2589355", "data2": "3008709", "data3": "3336059", "data4": "7079979", "data5": "9301340"},
        {"data1": "-143", "data2": "162", "data3": "109", "data4": "1122", "data5": "314"},
        {"data1": "65670", "data2": "327260", "data3": "436011", "data4": "3767778", "data5": "5734259"},
        {"data1": "-849", "data2": "3983", "data3": "332", "data4": "7641", "data5": "522"},
        {"data1": "144734", "data2": "336214", "data3": "442610", "data4": "2937723", "data5": "4272591"},
        {"data1": "-736", "data2": "1323", "data3": "316", "data4": "5637", "data5": "454"},
    ],
    "output3": [
        {"data1": "452335", "data2": "753568", "data3": "905276", "data4": "4306887", "data5": "6298333"},
        {"data1": "21310", "data2": "49500", "data3": "66050", "data4": "443617", "data5": "642957"},
        {"data1": "-736", "data2": "1323", "data3": "334", "data4": "5716", "data5": "449"},
        {"data1": "368", "data2": "107", "data3": "182", "data4": "61", "data5": "42"},
    ],
    "output4": [
        {"dt": "2023.12"}, {"dt": "2024.12"}, {"dt": "2025.12"}, {"dt": "2026.12E"}, {"dt": "2027.12E"},
    ],
}


class RoutingStubClient:
    """client.get 경계 — tr_id(차트는 period)로 fixture body 라우팅. fail 집합은 예외 주입."""

    def __init__(self, bodies, fail=None, env="real"):
        self._bodies = bodies
        self._fail = set(fail or ())
        self.env = env
        self.calls = []

    def get(self, tr_id, path, params, extra_headers=None):
        self.calls.append({"tr_id": tr_id, "path": path, "params": params})
        if tr_id in self._fail:
            raise RuntimeError(f"injected failure: {tr_id}")
        if tr_id == "FHKST03010100":  # 일봉/월봉 동일 TR — period 로 구분
            key = ("FHKST03010100", params.get("FID_PERIOD_DIV_CODE"))
            return self._bodies[key]
        return self._bodies[tr_id]


@pytest.fixture
def bodies(load_fixture):
    return {
        "CTPF1002R": load_fixture("kis_search_stock_info"),
        "FHKST01010100": load_fixture("kis_inquire_price"),
        "FHKST66430200": load_fixture("kis_income_statement"),
        "FHKST66430300": load_fixture("kis_financial_ratio"),
        ("FHKST03010100", "D"): load_fixture("kis_daily_chart"),
        ("FHKST03010100", "M"): load_fixture("kis_monthly_chart"),
        "HHKST668300C0": _ESTIMATE_BODY,
    }


def _judgement_contraction():
    """수축 국면(per_max=20, 가장 느슨한 적극매수 게이트) — regime_gate 는 regime+params 소비."""
    return {
        "regime": "수축",
        "params": {"cash": 20, "single_cap": 5, "per_max": 20, "pbr_max": 2.0},
        "recommended_cash_ratio": 20,
        "confidence": "high",
    }


def _judgement_overheat():
    """과열 국면(per_max=None) → entry_blocked True(신규진입 차단, 무조건 통과 아님)."""
    return {
        "regime": "과열",
        "params": {"cash": 80, "single_cap": 0, "per_max": None, "pbr_max": None},
        "recommended_cash_ratio": 80,
        "confidence": "high",
    }


# ── collect_stock_bundle: 정상 경로 ──────────────────────────────────────────

def test_bundle_happy_path_contract_shape(bodies):
    client = RoutingStubClient(bodies)
    bundle = detail.collect_stock_bundle("005930", client, _judgement_contraction())

    assert set(bundle.keys()) == BUNDLE_KEYS
    assert bundle["ticker"] == "005930"
    assert bundle["basic"]["sector"] == "반도체와반도체장비"
    assert bundle["valuation"]["price"] == 70500.0
    assert bundle["chart"]["candles"]  # 일봉 시리즈 존재
    assert bundle["indicator_config"] == {"ma_period": 20, "rsi_period": 14}
    assert bundle["partial_failure"] == []
    # 예측 PER: 현재가(valuation.price) ÷ 예측 EPS(추정연도) 로 계산, 컨센서스 출처 동반.
    fv = bundle["forward_valuation"]
    fpers = {x["period"]: x["forward_per"] for x in fv["forward_per"]}
    assert set(fpers) == {"202612", "202712"}  # 추정 연도만
    assert fpers["202712"] == pytest.approx(bundle["valuation"]["price"] / 64295.7, abs=0.05)
    assert fv["recommendation"] == "매수"
    # 직전년도(2025 실적) PER = 현재가 ÷ 2025 EPS(6605) — 예측과 함께 표시용.
    assert fv["prev_year_period"] == "202512"
    assert fv["prev_year_per"] == pytest.approx(bundle["valuation"]["price"] / 6605.0, abs=0.05)


def test_bundle_estimate_failure_sets_forward_none(bodies):
    """예측실적 조회 실패 → forward_valuation=None + partial_failure 'estimate', 종목 섹션은 정상."""
    client = RoutingStubClient(bodies, fail={SECTION_TR["estimate"]})
    bundle = detail.collect_stock_bundle("005930", client, _judgement_contraction())

    assert bundle["forward_valuation"] is None
    assert "estimate" in bundle["partial_failure"]
    assert bundle["valuation"]["price"] == 70500.0  # 나머지 정상
    assert set(bundle.keys()) == BUNDLE_KEYS


def test_bundle_assembles_year_end_prices_from_monthly(bodies):
    """2차: financials 성공 시 결산기말 종가를 월봉으로 조립(period=stac_yymm→close)."""
    client = RoutingStubClient(bodies)
    bundle = detail.collect_stock_bundle("005930", client, _judgement_contraction())

    yep = bundle["financials"]["year_end_prices"]
    assert yep == {"202312": 78500.0, "202212": 55300.0, "202112": 78600.0}
    # 월봉이 실제로 period='M' 로 조회됐는지(회당 단일호출) 확인.
    monthly_calls = [c for c in client.calls
                     if c["tr_id"] == "FHKST03010100" and c["params"]["FID_PERIOD_DIV_CODE"] == "M"]
    assert len(monthly_calls) == 1


def test_bundle_wires_sections_into_summary_engine(bodies):
    """번들이 valuation·financials·chart 를 엔진에 정확히 배선하는지(값으로 검증)."""
    client = RoutingStubClient(bodies)
    bundle = detail.collect_stock_bundle("005930", client, _judgement_contraction())

    summary = bundle["summary"]
    # current_per 는 valuation.per 에서 → 배선 확인.
    assert summary["current_per"] == 12.34
    # pos_52w_pct 는 valuation w52 권위 (70500-49900)/(88000-49900)*100 ≈ 54.07.
    assert summary["pos_52w_pct"] == pytest.approx(54.07, abs=0.1)
    # 항상 고정 키 반환(누락=None).
    assert "rev_cagr" in summary and "valuation_label" in summary


def test_bundle_regime_gate_uses_valuation_and_judgement(bodies):
    client = RoutingStubClient(bodies)
    bundle = detail.collect_stock_bundle("005930", client, _judgement_contraction())

    gate = bundle["regime_gate"]
    assert gate["regime"] == "수축"
    assert gate["per_max"] == 20
    # 종목 PER 12.34 < 20 → 상한 이내.
    assert gate["per_over"] is False
    assert gate["entry_blocked"] is False


def test_bundle_overheat_regime_blocks_entry(bodies):
    """과열 per_max=None → entry_blocked True(안전 반전 방지 — 무조건 통과 아님)."""
    client = RoutingStubClient(bodies)
    bundle = detail.collect_stock_bundle("005930", client, _judgement_overheat())

    assert bundle["regime_gate"]["entry_blocked"] is True
    assert bundle["regime_gate"]["per_max"] is None


# ── collect_stock_bundle: 부분 실패 (4섹션 각각) ─────────────────────────────

@pytest.mark.parametrize("section", ["basic", "valuation", "financials", "chart"])
def test_bundle_section_failure_isolated(bodies, section):
    """한 섹션 fetch 예외 → 그 섹션 null + partial_failure 기록, 나머지 정상, 항상 dict 반환."""
    client = RoutingStubClient(bodies, fail={SECTION_TR[section]})
    bundle = detail.collect_stock_bundle("005930", client, _judgement_contraction())

    assert bundle[section] is None
    assert section in bundle["partial_failure"]
    # 나머지 섹션은 살아있다.
    others = {"basic", "valuation", "financials", "chart"} - {section}
    for other in others:
        assert bundle[other] is not None, f"{other} 가 {section} 실패에 휩쓸려 죽음"
    # 계약 shape 은 항상 유지(라우트는 200).
    assert set(bundle.keys()) == BUNDLE_KEYS


def test_bundle_degraded_when_financials_output_empty(bodies, load_fixture):
    """'성공했으나 빈 재무'(신규상장) → financials 핵심값 전부 None → partial_failure 승격."""
    empty = dict(bodies)
    empty["FHKST66430200"] = {"rt_cd": "0", "output": []}
    empty["FHKST66430300"] = {"rt_cd": "0", "output": []}
    client = RoutingStubClient(empty)

    bundle = detail.collect_stock_bundle("005930", client, _judgement_contraction())

    assert "financials" in bundle["partial_failure"]  # degraded 승격
    # financials 섹션 자체는 fetch 성공이라 None 이 아니라 빈 구조.
    assert bundle["financials"] is not None


def test_bundle_regime_none_records_partial_failure(bodies):
    """judgement None(매크로 수집 실패) → regime_gate=None + partial_failure 에 'regime'."""
    client = RoutingStubClient(bodies)
    bundle = detail.collect_stock_bundle("005930", client, judgement=None)

    assert bundle["regime_gate"] is None
    assert "regime" in bundle["partial_failure"]


# ── 캐시 3원칙 격리 (spy_cache) ──────────────────────────────────────────────

def test_bundle_caches_only_financials_and_basic_meta(bodies, spy_cache):
    client = RoutingStubClient(bodies)
    detail.collect_stock_bundle("005930", client, _judgement_contraction(), cache=spy_cache)

    cached_keys = {key for (key, _v, _ttl) in spy_cache.set_calls}
    assert cached_keys == {
        "stock:meta:005930:financials",
        "stock:meta:005930:basic",
    }


def test_bundle_never_caches_valuation__plan_principle1(bodies, spy_cache):
    """원칙1: 현재가·PER·52주(valuation)은 어떤 키로도 캐시되지 않는다."""
    client = RoutingStubClient(bodies)
    detail.collect_stock_bundle("005930", client, _judgement_contraction(), cache=spy_cache)

    for key, value, _ttl in spy_cache.set_calls:
        assert not key.startswith("stock:price")
        assert not key.endswith(":valuation")
        # valuation 페이로드(현재가 70500)가 캐시에 실리지 않았는지.
        assert not (isinstance(value, dict) and value.get("price") == 70500.0)


def test_bundle_degraded_financials_not_cached__plan_principle2(bodies, spy_cache):
    """원칙2: degraded(빈 재무)면 financials·basic 모두 저장 안 함(명시 게이트)."""
    empty = dict(bodies)
    empty["FHKST66430200"] = {"rt_cd": "0", "output": []}
    empty["FHKST66430300"] = {"rt_cd": "0", "output": []}
    client = RoutingStubClient(empty)

    detail.collect_stock_bundle("005930", client, _judgement_contraction(), cache=spy_cache)

    assert spy_cache.set_calls == []


def test_bundle_financials_failure_skips_all_meta_cache__plan_principle2(bodies, spy_cache):
    """원칙2: financials fetch 실패 → financials 뿐 아니라 basic 도 저장 안 함(게이트로 묶임)."""
    client = RoutingStubClient(bodies, fail={SECTION_TR["financials"]})
    detail.collect_stock_bundle("005930", client, _judgement_contraction(), cache=spy_cache)

    assert spy_cache.set_calls == []


# ── 라우트 GET /api/detail/{ticker}/bundle ───────────────────────────────────

def _route_client(monkeypatch, bodies_map, judgement="ok", fail=None):
    stub = RoutingStubClient(bodies_map, fail=fail)
    monkeypatch.setattr(detail, "_resolve_client", lambda *a, **k: stub)
    if judgement == "raise":
        def boom():
            raise RuntimeError("FRED down")
        monkeypatch.setattr(detail, "_build_judgement", boom)
    else:
        monkeypatch.setattr(detail, "_build_judgement", _judgement_contraction)
    return TestClient(main.app)


def test_route_returns_bundle_contract(monkeypatch, bodies):
    client = _route_client(monkeypatch, bodies)
    resp = client.get("/api/detail/005930/bundle")

    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == BUNDLE_KEYS
    assert body["valuation"]["price"] == 70500.0
    assert body["regime_gate"]["regime"] == "수축"
    assert body["indicator_config"] == {"ma_period": 20, "rsi_period": 14}
    assert body["partial_failure"] == []


def test_route_regime_failure_sets_partial_failure(monkeypatch, bodies):
    """매크로 수집 실패 → 항상 200 + regime_gate=None + partial_failure 에 'regime'."""
    client = _route_client(monkeypatch, bodies, judgement="raise")
    resp = client.get("/api/detail/005930/bundle")

    assert resp.status_code == 200
    body = resp.json()
    assert body["regime_gate"] is None
    assert "regime" in body["partial_failure"]
    # 매크로가 죽어도 종목 섹션은 정상.
    assert body["valuation"]["price"] == 70500.0
