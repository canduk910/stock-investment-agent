"""워치리스트 뷰 서비스 — plan §"watchlist/service.py"·Phase 2.

build_watchlist_view(store, user_id, kis_client, judgement) -> dict.
핵심 계약(테스트가 스펙):
- 종목별 inquire_price 병렬 조회(캐시 없음, 원칙1) → 종목별 regime_gate(valuation, judgement) 재사용.
- entry_signal 은 regime_gate 파생(entry_blocked/per_over/pbr_over/single_cap/entry_allowed/note).
- **regime-agnostic 회귀(핵심)**: 과열 judgement(single_cap=0→per_max None→entry_blocked)와
  수축 judgement(single_cap=5,per_max=20→미차단) 둘 다 검증. 국면명 하드코딩 0 — 엔진이
  계산한 single_cap/entry_blocked 를 소비만.
- distance_to_target=(current-target)/target*100(target 없으면 None).
- target_status ∈ {reached(current≤target), near(≤target*(1+thr)), far, none(target 없음)}.
- 시세 실패 종목 → 값 None + partial_failure 에 ticker(번들 철학, 나머지 정상).
- judgement=None → 모든 entry_signal=None + partial_failure 에 "regime".
"""
from __future__ import annotations

import pytest

from macro.engine import REGIME_PARAMS
from watchlist.constants import NEAR_TARGET_THRESHOLD_PCT
from watchlist.models import WatchlistItem
from watchlist.store import InMemoryWatchlistStore
from watchlist import service as svc


# ── judgement fixture(엔진 계약: regime + params) ────────────────────────────

def _judgement(regime: str) -> dict:
    """judge_regime 반환의 최소 부분집합(service·regime_gate 가 쓰는 키만)."""
    return {"regime": regime, "params": dict(REGIME_PARAMS[regime])}


OVERHEAT = _judgement("과열")   # single_cap=0, per_max=None → entry_blocked
CONTRACTION = _judgement("수축")  # single_cap=5, per_max=20, pbr_max=2.0 → 미차단


# ── StubClient + inquire_price 스텁(경계만 mock) ─────────────────────────────

class StubClient:
    """KIS 클라이언트 자리표시자 — 실제 호출은 inquire_price 스텁이 가로챈다."""


def _valuation(price, change_rate, per, pbr):
    """inquire_price.inquire_price 반환 계약(normalize_price)."""
    return {
        "ticker": None, "price": price, "change_rate": change_rate,
        "per": per, "pbr": pbr, "eps": None, "bps": None,
        "week52_high": None, "week52_low": None, "market_cap": None, "as_of": None,
    }


@pytest.fixture
def patch_prices(monkeypatch):
    """{ticker: valuation dict 또는 Exception} 매핑으로 inquire_price 를 대체."""

    def _apply(mapping):
        def _fake(client, ticker, market="J"):
            result = mapping[ticker]
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(svc.inquire_price, "inquire_price", _fake)

    return _apply


def _store_with(*items) -> InMemoryWatchlistStore:
    store = InMemoryWatchlistStore()
    for it in items:
        store.put(it)
    return store


def _item(ticker, added_at, **kw):
    return WatchlistItem(ticker=ticker, stock_name=kw.pop("stock_name", ticker),
                         added_at=added_at, **kw)


def _by_ticker(view):
    return {i["ticker"]: i for i in view["items"]}


# ── 반환 shape·regime 블록 ───────────────────────────────────────────────────

def test_returns_fixed_keys(patch_prices):
    patch_prices({"005930": _valuation(80000, 1.2, 12.0, 1.1)})
    store = _store_with(_item("005930", "2026-01-01T00:00:00+00:00"))
    view = svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION)
    assert set(view.keys()) == {"items", "regime", "partial_failure"}
    assert view["regime"] == {"regime": "수축", "single_cap": 5, "entry_blocked": False}


def test_empty_watchlist(patch_prices):
    patch_prices({})
    store = InMemoryWatchlistStore()
    view = svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION)
    assert view["items"] == []
    assert view["partial_failure"] == []


def test_item_carries_stored_fields(patch_prices):
    patch_prices({"005930": _valuation(80000, 1.2, 12.0, 1.1)})
    store = _store_with(_item("005930", "2026-01-01T00:00:00+00:00",
                              stock_name="삼성전자", reason="저평가", target_price=90000.0))
    view = svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION)
    it = _by_ticker(view)["005930"]
    assert it["stock_name"] == "삼성전자"
    assert it["reason"] == "저평가"
    assert it["target_price"] == 90000.0
    assert it["added_at"] == "2026-01-01T00:00:00+00:00"
    # 라이브 시세 병합.
    assert it["current_price"] == 80000
    assert it["change_rate"] == 1.2
    assert it["per"] == 12.0
    assert it["pbr"] == 1.1


def test_items_ordered_registered(patch_prices):
    patch_prices({
        "005930": _valuation(80000, 1.0, 12.0, 1.1),
        "000660": _valuation(200000, 2.0, 10.0, 1.3),
    })
    store = _store_with(
        _item("000660", "2026-02-01T00:00:00+00:00", stock_name="SK하이닉스"),
        _item("005930", "2026-01-01T00:00:00+00:00"),
    )
    view = svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION)
    assert [i["ticker"] for i in view["items"]] == ["005930", "000660"]  # added_at 오름차순


# ── entry_signal — 수축(미차단) ──────────────────────────────────────────────

def test_entry_signal_contraction_within_limits(patch_prices):
    # per 10 ≤ 20, pbr 1.0 ≤ 2.0 → 진입 검토 가능.
    patch_prices({"005930": _valuation(80000, 1.0, 10.0, 1.0)})
    store = _store_with(_item("005930", "2026-01-01T00:00:00+00:00"))
    view = svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION)
    sig = _by_ticker(view)["005930"]["entry_signal"]
    assert sig["single_cap"] == 5
    assert sig["entry_blocked"] is False
    assert sig["per_over"] is False
    assert sig["pbr_over"] is False
    assert sig["entry_allowed"] is True
    assert isinstance(sig["note"], str) and sig["note"]


def test_entry_signal_contraction_per_over(patch_prices):
    # per 25 > 20 → per_over → 미허용(차단은 아님).
    patch_prices({"005930": _valuation(80000, 1.0, 25.0, 1.0)})
    store = _store_with(_item("005930", "2026-01-01T00:00:00+00:00"))
    view = svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION)
    sig = _by_ticker(view)["005930"]["entry_signal"]
    assert sig["entry_blocked"] is False
    assert sig["per_over"] is True
    assert sig["entry_allowed"] is False


# ── entry_signal — 과열(entry_blocked) : regime-agnostic 회귀 ────────────────

def test_entry_signal_overheat_blocks_regardless_of_valuation(patch_prices):
    # 과열 국면은 밸류에이션과 무관하게 entry_blocked=True(single_cap=0). 매우 싼 종목도 차단.
    patch_prices({"005930": _valuation(80000, 1.0, 3.0, 0.5)})
    store = _store_with(_item("005930", "2026-01-01T00:00:00+00:00"))
    view = svc.build_watchlist_view(store, "local", StubClient(), OVERHEAT)
    sig = _by_ticker(view)["005930"]["entry_signal"]
    assert sig["single_cap"] == 0
    assert sig["entry_blocked"] is True
    assert sig["entry_allowed"] is False
    assert view["regime"] == {"regime": "과열", "single_cap": 0, "entry_blocked": True}


def test_entry_signal_regime_agnostic_no_hardcoded_regime_name(patch_prices):
    # 같은 종목이 국면만 바꿔도 결과가 엔진 single_cap 을 따라간다(국면명 하드코딩 아님).
    patch_prices({"005930": _valuation(80000, 1.0, 10.0, 1.0)})
    store = _store_with(_item("005930", "2026-01-01T00:00:00+00:00"))
    overheat = _by_ticker(svc.build_watchlist_view(store, "local", StubClient(), OVERHEAT))["005930"]
    contraction = _by_ticker(svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION))["005930"]
    assert overheat["entry_signal"]["entry_blocked"] is True
    assert contraction["entry_signal"]["entry_blocked"] is False


# ── distance_to_target · target_status ───────────────────────────────────────

def test_distance_to_target_computed(patch_prices):
    # current 88000, target 80000 → (88000-80000)/80000*100 = +10%
    patch_prices({"005930": _valuation(88000, 1.0, 10.0, 1.0)})
    store = _store_with(_item("005930", "2026-01-01T00:00:00+00:00", target_price=80000.0))
    it = _by_ticker(svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION))["005930"]
    assert it["distance_to_target"] == pytest.approx(10.0)


def test_target_status_none_when_no_target(patch_prices):
    patch_prices({"005930": _valuation(80000, 1.0, 10.0, 1.0)})
    store = _store_with(_item("005930", "2026-01-01T00:00:00+00:00", target_price=None))
    it = _by_ticker(svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION))["005930"]
    assert it["distance_to_target"] is None
    assert it["target_status"] == "none"


def test_target_status_reached_when_at_or_below(patch_prices):
    # current 79000 ≤ target 80000 → reached.
    patch_prices({"005930": _valuation(79000, 1.0, 10.0, 1.0)})
    store = _store_with(_item("005930", "2026-01-01T00:00:00+00:00", target_price=80000.0))
    it = _by_ticker(svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION))["005930"]
    assert it["target_status"] == "reached"


def test_target_status_near_within_threshold(patch_prices):
    # thr=3% 기준. current 82000, target 80000 → +2.5% ≤ 3% → near.
    patch_prices({"005930": _valuation(82000, 1.0, 10.0, 1.0)})
    store = _store_with(_item("005930", "2026-01-01T00:00:00+00:00", target_price=80000.0))
    it = _by_ticker(svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION))["005930"]
    assert NEAR_TARGET_THRESHOLD_PCT == 3.0  # 임계 SSOT 확인
    assert it["target_status"] == "near"


def test_target_status_far_beyond_threshold(patch_prices):
    # current 90000, target 80000 → +12.5% > 3% → far.
    patch_prices({"005930": _valuation(90000, 1.0, 10.0, 1.0)})
    store = _store_with(_item("005930", "2026-01-01T00:00:00+00:00", target_price=80000.0))
    it = _by_ticker(svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION))["005930"]
    assert it["target_status"] == "far"


def test_target_status_zero_target_is_none(patch_prices):
    # target_price=0(ge=0 저장 가능) → distance None 인데 status 도 'none'이어야 한다
    # (프론트 classifyTargetStatus·백엔드 _distance_to_target 과 동일 계약). 회귀 방지(IMP-01).
    patch_prices({"005930": _valuation(80000, 1.0, 10.0, 1.0)})
    store = _store_with(_item("005930", "2026-01-01T00:00:00+00:00", target_price=0.0))
    it = _by_ticker(svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION))["005930"]
    assert it["distance_to_target"] is None
    assert it["target_status"] == "none"


def test_target_status_reached_at_exact_target(patch_prices):
    # current == target(경계 포함) → reached.
    patch_prices({"005930": _valuation(80000, 1.0, 10.0, 1.0)})
    store = _store_with(_item("005930", "2026-01-01T00:00:00+00:00", target_price=80000.0))
    it = _by_ticker(svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION))["005930"]
    assert it["target_status"] == "reached"


def test_target_status_near_exact_threshold_boundary(patch_prices):
    # 정확히 +3%(80000*1.03=82400)는 near(경계 포함), 한 틱 위(82401)는 far — 부등호 회귀 고정.
    patch_prices({"005930": _valuation(82400, 1.0, 10.0, 1.0)})
    store = _store_with(_item("005930", "2026-01-01T00:00:00+00:00", target_price=80000.0))
    near = _by_ticker(svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION))["005930"]
    assert near["target_status"] == "near"

    patch_prices({"005930": _valuation(82401, 1.0, 10.0, 1.0)})
    far = _by_ticker(svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION))["005930"]
    assert far["target_status"] == "far"


# ── 부분 실패 보존 ───────────────────────────────────────────────────────────

def test_price_failure_preserves_partial(patch_prices):
    # 000660 시세 실패 → 값 None + partial_failure 에 ticker. 005930 은 정상.
    patch_prices({
        "005930": _valuation(80000, 1.0, 10.0, 1.0),
        "000660": RuntimeError("KIS timeout"),
    })
    store = _store_with(
        _item("005930", "2026-01-01T00:00:00+00:00"),
        _item("000660", "2026-02-01T00:00:00+00:00", stock_name="SK하이닉스"),
    )
    view = svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION)
    items = _by_ticker(view)
    assert items["005930"]["current_price"] == 80000
    assert items["000660"]["current_price"] is None
    assert items["000660"]["per"] is None
    assert items["000660"]["entry_signal"] is None  # 시세 없으면 게이트 불가
    assert "000660" in view["partial_failure"]
    assert "005930" not in view["partial_failure"]
    # 실패 종목도 저장 필드(이름/사유)는 유지 — 목록에서 사라지지 않는다.
    assert items["000660"]["stock_name"] == "SK하이닉스"


# ── judgement 결측 → regime degraded ─────────────────────────────────────────

def test_no_judgement_degrades_regime(patch_prices):
    patch_prices({"005930": _valuation(80000, 1.0, 10.0, 1.0)})
    store = _store_with(_item("005930", "2026-01-01T00:00:00+00:00"))
    view = svc.build_watchlist_view(store, "local", StubClient(), None)
    it = _by_ticker(view)["005930"]
    # 시세는 정상(진입신호만 판정 불가).
    assert it["current_price"] == 80000
    assert it["entry_signal"] is None
    assert "regime" in view["partial_failure"]
    assert view["regime"] is None


# ── 병렬 시세 동시성 상한(IMP-09: KIS 레이트리밋 보호) ────────────────────────

def test_worker_count_capped_at_concurrency_limit():
    from watchlist.constants import WATCHLIST_FETCH_CONCURRENCY as CAP
    assert svc._worker_count(1) == 1
    assert svc._worker_count(3) == 3
    assert svc._worker_count(30) == CAP   # 종목 많아도 상한으로 캡(폭주 방지)
    assert svc._worker_count(CAP) == CAP
    assert svc._worker_count(0) == 1      # 방어(빈 목록은 호출 전 early return)
