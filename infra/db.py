"""SQLAlchemy DB 기반 — 로컬 SQLite(기본) / 프로덕션 GCP Cloud SQL for PostgreSQL.

`DATABASE_URL` env 로 스왑한다(로컬 기본 `sqlite:///.cache/app.db`, 프로덕션
`postgresql+psycopg://user:pw@host/db`). 방언 중립 ORM(String/Integer/DateTime/JSON) →
SQLite↔Postgres 무변경. 스키마는 Phase 마다 **신규 테이블 추가**라 `init_db()`(startup)의
`create_all` 로 충분(기존 테이블 alter 없음). 프로덕션 마이그레이션은 Alembic(향후).

FastAPI 의존성 `get_db` 는 요청 스코프 Session 을 yield/close 한다. 테스트는
`app.dependency_overrides[get_db]` 로 인메모리 SQLite Session 을 주입한다.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
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
    """모델 등록 후 테이블 생성(존재하면 skip). startup 에서 호출."""
    import_models()
    Base.metadata.create_all(get_engine())


def import_models() -> None:
    """ORM 모델 모듈을 import 해 Base.metadata 에 테이블을 등록한다(create_all 전 필수).

    Phase 마다 신규 모델을 여기에 추가한다(단일 등록 지점).
    """
    from auth import models as _auth_models  # noqa: F401  (User)
    from watchlist import db_models as _wl_models  # noqa: F401  (WatchlistItemRow)
    from chat import history_models as _hist_models  # noqa: F401  (Conversation, ChatMessage)


def get_db():
    """요청 스코프 DB Session(yield/close). FastAPI Depends 용."""
    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
