"""워치리스트 뷰 서비스 — plan §"watchlist/service.py"·Phase 2.

build_watchlist_view(store, user_id, kis_client, judgement) -> dict.
핵심 계약(테스트가 스펙):
- 종목별 inquire_price 병렬 조회(캐시 없음, 원칙1) → 시세·등락·목표가 상태·스파크라인 조립.
- 국면별 종목 진입게이트(entry_signal)는 폐기(항목3) — 국면은 현금비중만 관리하고 종목별
  PER/PBR/편입비중 커트는 없다. item 에 entry_signal 필드 없음, regime 블록은 {regime} 만.
- distance_to_target=(current-target)/target*100(target 없으면 None).
- target_status ∈ {reached(current≤target), near(≤target*(1+thr)), far, none(target 없음)}.
- 시세 실패 종목 → 값 None + partial_failure 에 ticker(번들 철학, 나머지 정상).
- judgement=None → regime=None + partial_failure 에 "regime"(국면명 degraded).
"""
from __future__ import annotations

import pytest

from macro.engine import REGIME_PARAMS
from watchlist.constants import NEAR_TARGET_THRESHOLD_PCT
from watchlist.models import WatchlistItem
from watchlist.store import InMemoryWatchlistStore
from watchlist import service as svc


# ── judgement fixture(엔진 계약: regime + params[cash]) ──────────────────────

def _judgement(regime: str) -> dict:
    """judge_regime 반환의 최소 부분집합(service 가 쓰는 regime + params[cash])."""
    return {"regime": regime, "params": dict(REGIME_PARAMS[regime])}


OVERHEAT = _judgement("과열")   # 현금비중 80%
CONTRACTION = _judgement("수축")  # 현금비중 20%


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


def _chart(closes, start_date="20260101"):
    """normalize_daily_chart 반환 계약: {ticker, candles:[{date, close, ...}]}.

    closes 를 date 오름차순으로 candle 화(스파크라인 종가 시계열 원천). 서비스가
    date 로 정렬하는지 확인하려고 일부 테스트는 역순 입력을 준다.
    """
    candles = []
    for i, close in enumerate(closes):
        candles.append({
            "date": f"2026010{i}" if i < 10 else f"202601{i}",
            "open": None, "high": None, "low": None,
            "close": close, "volume": None,
        })
    return {"ticker": None, "candles": candles}


@pytest.fixture
def patch_charts(monkeypatch):
    """{ticker: chart dict 또는 Exception} 매핑으로 chart.inquire_daily_itemchartprice 대체."""

    def _apply(mapping):
        def _fake(client, ticker, start_date, end_date, period="D", adj_price="1", market="J"):
            result = mapping[ticker]
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(svc.chart, "inquire_daily_itemchartprice", _fake)

    return _apply


@pytest.fixture(autouse=True)
def _default_no_chart(monkeypatch):
    """spark 를 명시 설정하지 않은 기존 테스트에서 chart 호출이 실 KIS 를 타지 않게 기본 무력화.

    기본은 예외 → 서비스가 graceful 하게 spark=None 으로 처리(기존 테스트 assertion 불변).
    patch_charts 를 쓰는 테스트는 이 기본을 덮어쓴다.
    """
    def _boom(*a, **k):
        raise RuntimeError("chart not stubbed")

    monkeypatch.setattr(svc.chart, "inquire_daily_itemchartprice", _boom)


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
    assert view["regime"] == {"regime": "수축"}  # 국면명만(진입게이트 폐기 — single_cap/entry_blocked 제거)
    assert "entry_signal" not in _by_ticker(view)["005930"]  # 종목 진입신호 없음


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


# 국면별 진입신호(entry_signal)는 폐기(항목3) — 관련 테스트 제거. 국면은 현금비중만, 종목별 커트 없음.
# regime 블록은 국면명만, item 에는 entry_signal 필드가 없다(위 test_returns_fixed_keys 로 커버).


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
    assert it["current_price"] == 80000  # 시세는 정상
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


# ── 스파크라인 시계열(Phase D — spark:number[]|null) ─────────────────────────

def test_spark_is_close_series(patch_prices, patch_charts):
    # 일봉 종가를 date 오름차순 number[] 로 노출(프론트 미니차트 원천).
    patch_prices({"005930": _valuation(80000, 1.0, 10.0, 1.0)})
    patch_charts({"005930": _chart([100.0, 110.0, 105.0, 120.0])})
    store = _store_with(_item("005930", "2026-01-01T00:00:00+00:00"))
    it = _by_ticker(svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION))["005930"]
    assert it["spark"] == [100.0, 110.0, 105.0, 120.0]


def test_spark_sorted_by_date_ascending(patch_prices, patch_charts):
    # KIS 가 최신순(내림차순)으로 줄 수 있어 서비스가 date 오름차순 정렬(부호/추세 뒤집힘 방지).
    patch_prices({"005930": _valuation(80000, 1.0, 10.0, 1.0)})
    reversed_chart = {"ticker": None, "candles": [
        {"date": "20260103", "close": 120.0},
        {"date": "20260101", "close": 100.0},
        {"date": "20260102", "close": 110.0},
    ]}
    patch_charts({"005930": reversed_chart})
    store = _store_with(_item("005930", "2026-01-01T00:00:00+00:00"))
    it = _by_ticker(svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION))["005930"]
    assert it["spark"] == [100.0, 110.0, 120.0]  # date 오름차순


def test_spark_limited_to_recent_points(patch_prices, patch_charts):
    from watchlist.constants import WATCHLIST_SPARK_POINTS as N
    # N개보다 많으면 최근 N개(꼬리)만 — 미니차트 과밀 방지.
    closes = [float(i) for i in range(N + 10)]
    patch_prices({"005930": _valuation(80000, 1.0, 10.0, 1.0)})
    patch_charts({"005930": _chart(closes)})
    store = _store_with(_item("005930", "2026-01-01T00:00:00+00:00"))
    it = _by_ticker(svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION))["005930"]
    assert len(it["spark"]) == N
    assert it["spark"] == closes[-N:]  # 최근 N개(가장 최신이 끝)


def test_spark_none_on_chart_failure(patch_prices, patch_charts):
    # 일봉 조회 실패 → spark=None(graceful). 전체를 죽이지 않고 시세·진입신호는 정상.
    patch_prices({"005930": _valuation(80000, 1.0, 10.0, 1.0)})
    patch_charts({"005930": RuntimeError("chart timeout")})
    store = _store_with(_item("005930", "2026-01-01T00:00:00+00:00"))
    it = _by_ticker(svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION))["005930"]
    assert it["spark"] is None
    assert it["current_price"] == 80000  # 시세는 정상


def test_spark_none_on_empty_candles(patch_prices, patch_charts):
    # 캔들 없음(신규상장·데이터 없음) → spark=None(빈 리스트 아님 — 프론트 렌더 분기 단순화).
    patch_prices({"005930": _valuation(80000, 1.0, 10.0, 1.0)})
    patch_charts({"005930": {"ticker": None, "candles": []}})
    store = _store_with(_item("005930", "2026-01-01T00:00:00+00:00"))
    it = _by_ticker(svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION))["005930"]
    assert it["spark"] is None


def test_spark_drops_none_closes(patch_prices, patch_charts):
    # 종가 결측 candle 은 제외(None 이 시계열에 섞이면 프론트 스케일 계산이 깨진다).
    patch_prices({"005930": _valuation(80000, 1.0, 10.0, 1.0)})
    mixed = {"ticker": None, "candles": [
        {"date": "20260101", "close": 100.0},
        {"date": "20260102", "close": None},
        {"date": "20260103", "close": 120.0},
    ]}
    patch_charts({"005930": mixed})
    store = _store_with(_item("005930", "2026-01-01T00:00:00+00:00"))
    it = _by_ticker(svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION))["005930"]
    assert it["spark"] == [100.0, 120.0]


def test_spark_per_item_independent(patch_prices, patch_charts):
    # 한 종목 spark 실패가 다른 종목 spark 를 죽이지 않는다(per-item graceful).
    patch_prices({
        "005930": _valuation(80000, 1.0, 10.0, 1.0),
        "000660": _valuation(200000, 2.0, 12.0, 1.3),
    })
    patch_charts({
        "005930": _chart([100.0, 110.0]),
        "000660": RuntimeError("chart fail"),
    })
    store = _store_with(
        _item("005930", "2026-01-01T00:00:00+00:00"),
        _item("000660", "2026-02-01T00:00:00+00:00", stock_name="SK하이닉스"),
    )
    items = _by_ticker(svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION))
    assert items["005930"]["spark"] == [100.0, 110.0]
    assert items["000660"]["spark"] is None


def test_spark_failure_not_in_partial_failure(patch_prices, patch_charts):
    # 스파크라인은 선택적 시각화 — spark 실패는 partial_failure 를 오염시키지 않는다(시세 실패 semantics 보존).
    patch_prices({"005930": _valuation(80000, 1.0, 10.0, 1.0)})
    patch_charts({"005930": RuntimeError("chart fail")})
    store = _store_with(_item("005930", "2026-01-01T00:00:00+00:00"))
    view = svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION)
    assert "005930" not in view["partial_failure"]  # 시세는 성공했으므로


def test_price_failure_still_attempts_spark(patch_prices, patch_charts):
    # 시세 실패 종목도 spark 는 독립 조회(시세 None 이어도 미니차트는 보여줄 수 있다).
    patch_prices({"005930": RuntimeError("price fail")})
    patch_charts({"005930": _chart([100.0, 110.0])})
    store = _store_with(_item("005930", "2026-01-01T00:00:00+00:00"))
    view = svc.build_watchlist_view(store, "local", StubClient(), CONTRACTION)
    it = _by_ticker(view)["005930"]
    assert it["current_price"] is None
    assert "005930" in view["partial_failure"]  # 시세 실패는 여전히 기록
    assert it["spark"] == [100.0, 110.0]         # spark 는 독립 성공
