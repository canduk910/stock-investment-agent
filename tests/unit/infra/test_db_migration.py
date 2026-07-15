"""경량 additive-column 마이그레이션 — `_run_lightweight_migrations`.

create_all 은 기존 테이블에 컬럼을 못 붙인다. 매수/매도 목표가 분리로 watchlist_items 에
sell_target_price 를 추가하는데, 이미 배포된 DB(구 스키마 테이블)에도 적용돼야 한다.
계약: 구 스키마 테이블 → 컬럼 추가 · 이미 있으면 no-op(idempotent) · 테이블 없으면 skip.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from infra.db import _run_lightweight_migrations


def _cols(engine, table):
    return {c["name"] for c in inspect(engine).get_columns(table)}


def test_adds_missing_sell_target_price(tmp_path):
    # 구 스키마(sell_target_price 없는 watchlist_items)를 raw DDL 로 만든다.
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}", future=True)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE watchlist_items ("
            "id INTEGER PRIMARY KEY, user_id VARCHAR, ticker VARCHAR, "
            "stock_name VARCHAR, reason VARCHAR, target_price FLOAT, added_at VARCHAR)"
        ))
    assert "sell_target_price" not in _cols(engine, "watchlist_items")

    _run_lightweight_migrations(engine)
    assert "sell_target_price" in _cols(engine, "watchlist_items")


def test_idempotent_when_column_present(tmp_path):
    # 이미 컬럼이 있는 테이블 → 재실행해도 예외 없이 no-op.
    engine = create_engine(f"sqlite:///{tmp_path / 'new.db'}", future=True)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE watchlist_items ("
            "id INTEGER PRIMARY KEY, user_id VARCHAR, ticker VARCHAR, "
            "stock_name VARCHAR, reason VARCHAR, target_price FLOAT, "
            "sell_target_price FLOAT, added_at VARCHAR)"
        ))
    _run_lightweight_migrations(engine)  # no-op
    _run_lightweight_migrations(engine)  # 두 번째도 안전
    assert "sell_target_price" in _cols(engine, "watchlist_items")


def test_skips_when_table_absent(tmp_path):
    # watchlist_items 테이블이 아예 없으면 skip(신규 DB는 create_all 이 컬럼 포함 생성).
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}", future=True)
    _run_lightweight_migrations(engine)  # 예외 없이 통과
    assert not inspect(engine).has_table("watchlist_items")
