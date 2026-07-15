"""SQLAlchemy DB 기반 — 로컬 SQLite(기본) / 프로덕션 GCP Cloud SQL for PostgreSQL.

`DATABASE_URL` env 로 스왑한다(로컬 기본 `sqlite:///.cache/app.db`, 프로덕션
`postgresql+psycopg://user:pw@host/db`). 방언 중립 ORM(String/Integer/DateTime/JSON) →
SQLite↔Postgres 무변경. 스키마는 대부분 **신규 테이블 추가**라 `init_db()`(startup)의
`create_all` 로 충분하지만, **기존 테이블에 컬럼을 추가**할 땐 create_all 이 alter 를 안 하므로
`_run_lightweight_migrations()`(부재 컬럼만 idempotent `ADD COLUMN`, `_ADDITIVE_COLUMNS` 단일
출처)가 붙인다. 본격 마이그레이션(rename/drop/제약)은 Alembic(향후).

FastAPI 의존성 `get_db` 는 요청 스코프 Session 을 yield/close 한다. 테스트는
`app.dependency_overrides[get_db]` 로 인메모리 SQLite Session 을 주입한다.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DEFAULT_DATABASE_URL = "sqlite:///.cache/app.db"


class Base(DeclarativeBase):
    """모든 ORM 모델의 공통 베이스(metadata 단일 출처)."""


_engine = None
_SessionLocal: sessionmaker | None = None


def _database_url() -> str:
    return os.environ.get("DATABASE_URL", "").strip() or DEFAULT_DATABASE_URL


def _connect_args(url: str) -> dict:
    # SQLite 는 FastAPI 스레드 공유를 위해 check_same_thread=False.
    return {"check_same_thread": False} if url.startswith("sqlite") else {}


def get_engine():
    global _engine
    if _engine is None:
        url = _database_url()
        if url.startswith("sqlite:///"):  # 파일 경로 부모 디렉토리 보장(.cache)
            path = url.replace("sqlite:///", "", 1)
            if path and path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(url, connect_args=_connect_args(url), future=True)
    return _engine


def get_sessionmaker() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(), autoflush=False, expire_on_commit=False, class_=Session
        )
    return _SessionLocal


def init_db() -> None:
    """모델 등록 후 테이블 생성(존재하면 skip) + 경량 컬럼 추가 마이그레이션. startup 에서 호출."""
    import_models()
    Base.metadata.create_all(get_engine())
    _run_lightweight_migrations()


# create_all 이 못 하는 '기존 테이블에 신규 컬럼 추가'만 다루는 최소 마이그레이션(Alembic 도입 전).
# (컬럼명, 컬럼 DDL 타입) — SQLite·Postgres 공용 타입만 사용(FLOAT 은 양쪽 다 지원).
_ADDITIVE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    # 매수/매도 목표가 분리(항목): watchlist_items 에 매도 목표가 컬럼 추가.
    ("watchlist_items", "sell_target_price", "FLOAT"),
)


def _run_lightweight_migrations(engine=None) -> None:
    """부재한 additive 컬럼만 `ALTER TABLE ADD COLUMN` (idempotent · SQLite/Postgres 공용).

    신규 DB 는 create_all 이 이미 컬럼 포함해 만들므로 no-op. 기존 DB(구 스키마 테이블)는
    부재 컬럼만 붙인다. `create_all` 은 기존 테이블을 alter 하지 않기 때문에 필요하다.
    """
    engine = engine or get_engine()
    inspector = inspect(engine)
    for table, column, ddl_type in _ADDITIVE_COLUMNS:
        if not inspector.has_table(table):
            continue  # 신규 DB — create_all 이 컬럼 포함해 생성(no-op)
        existing = {c["name"] for c in inspector.get_columns(table)}
        if column in existing:
            continue  # 이미 있음 — idempotent
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


def import_models() -> None:
    """ORM 모델 모듈을 import 해 Base.metadata 에 테이블을 등록한다(create_all 전 필수).

    Phase 마다 신규 모델을 여기에 추가한다(단일 등록 지점).
    """
    from auth import models as _auth_models  # noqa: F401  (User)
    from auth import kis_models as _kis_models  # noqa: F401  (KisCredentialRow, 유저별 암호화)
    from watchlist import db_models as _wl_models  # noqa: F401  (WatchlistItemRow)
    from chat import history_models as _hist_models  # noqa: F401  (Conversation, ChatMessage)
    from chat import report_models as _report_models  # noqa: F401  (AnalystReportRow, 공동)


def get_db():
    """요청 스코프 DB Session(yield/close). FastAPI Depends 용."""
    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
