"""WatchlistItem 모델 계약 — plan §"백엔드 신규: watchlist/models.py".

Red-first: ticker 정규식(`^[0-9A-Za-z]{6}$` — frontend/src/lib/ticker.js SSOT와 동일),
target_price 음수 거부(≥0), reason/target_price 옵션(None 허용), added_at ISO 문자열.
Pydantic 도입(P2 리포트 스키마와 공유 정신).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from watchlist.models import WatchlistItem


# ── ticker 정규식(ticker.js SSOT와 동일) ─────────────────────────────────────

@pytest.mark.parametrize("ticker", ["005930", "000660", "A12345", "abc123"])
def test_valid_ticker_accepted(ticker):
    item = WatchlistItem(ticker=ticker, stock_name="X", added_at="2026-07-09T00:00:00+00:00")
    assert item.ticker == ticker


@pytest.mark.parametrize("ticker", ["00593", "0059300", "005-93", "삼성전자", "", "00 930"])
def test_invalid_ticker_rejected(ticker):
    with pytest.raises(ValidationError):
        WatchlistItem(ticker=ticker, stock_name="X", added_at="2026-07-09T00:00:00+00:00")


# ── target_price ≥ 0 ─────────────────────────────────────────────────────────

def test_negative_target_price_rejected():
    with pytest.raises(ValidationError):
        WatchlistItem(
            ticker="005930", stock_name="삼성전자",
            target_price=-100.0, added_at="2026-07-09T00:00:00+00:00",
        )


def test_zero_and_positive_target_price_accepted():
    zero = WatchlistItem(ticker="005930", stock_name="X", target_price=0.0,
                         added_at="2026-07-09T00:00:00+00:00")
    pos = WatchlistItem(ticker="005930", stock_name="X", target_price=80000.0,
                        added_at="2026-07-09T00:00:00+00:00")
    assert zero.target_price == 0.0
    assert pos.target_price == 80000.0


def test_target_price_optional_defaults_none():
    item = WatchlistItem(ticker="005930", stock_name="X",
                         added_at="2026-07-09T00:00:00+00:00")
    assert item.target_price is None


# ── reason 옵션 ──────────────────────────────────────────────────────────────

def test_reason_optional_defaults_none():
    item = WatchlistItem(ticker="005930", stock_name="X",
                         added_at="2026-07-09T00:00:00+00:00")
    assert item.reason is None


def test_reason_string_accepted():
    item = WatchlistItem(ticker="005930", stock_name="X", reason="저평가 진입 후보",
                         added_at="2026-07-09T00:00:00+00:00")
    assert item.reason == "저평가 진입 후보"


# ── user_id 기본값(단일 로컬 사용자) ─────────────────────────────────────────

def test_user_id_defaults_to_local():
    item = WatchlistItem(ticker="005930", stock_name="X",
                         added_at="2026-07-09T00:00:00+00:00")
    assert item.user_id == "local"


# ── 직렬화 round-trip(store JSON 영속 대비) ──────────────────────────────────

def test_model_dump_round_trip():
    item = WatchlistItem(
        user_id="local", ticker="005930", stock_name="삼성전자",
        reason="목표가 접근 감시", target_price=90000.0,
        added_at="2026-07-09T00:00:00+00:00",
    )
    dumped = item.model_dump()
    restored = WatchlistItem(**dumped)
    assert restored == item
