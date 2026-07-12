"""대화기록 저장소 — 대화 CRUD·메시지·hydrate·**유저 격리**(인메모리 SQLite)."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from chat.history_store import HistoryStore
from infra.db import Base, import_models


@pytest.fixture
def store():
    import_models()  # Conversation, ChatMessage 등록
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    return HistoryStore(db)


def test_create_and_list_conversation(store):
    c = store.create_conversation("1", title="첫 대화")
    assert c.id is not None and c.title == "첫 대화"
    convs = store.list_conversations("1")
    assert [x.id for x in convs] == [c.id]


def test_get_conversation_ownership(store):
    c = store.create_conversation("1")
    assert store.get_conversation("1", c.id) is not None
    assert store.get_conversation("2", c.id) is None  # 남의 대화 안 보임


def test_add_turn_and_list_messages(store):
    c = store.create_conversation("1")
    store.add_turn(c.id, "안녕", "안녕하세요")
    msgs = store.list_messages(c.id)
    assert [(m.role, m.content) for m in msgs] == [
        ("user", "안녕"),
        ("assistant", "안녕하세요"),
    ]


def test_recent_messages_for_hydrate(store):
    c = store.create_conversation("1")
    for i in range(6):
        store.add_turn(c.id, f"q{i}", f"a{i}")  # 12 messages
    recent = store.recent_messages(c.id, 4)  # 최근 4개, 시간순
    assert recent == [
        {"role": "user", "content": "q4"},
        {"role": "assistant", "content": "a4"},
        {"role": "user", "content": "q5"},
        {"role": "assistant", "content": "a5"},
    ]


def test_delete_conversation_cascades(store):
    c = store.create_conversation("1")
    store.add_turn(c.id, "q", "a")
    assert store.delete_conversation("1", c.id) is True
    assert store.get_conversation("1", c.id) is None
    assert store.list_messages(c.id) == []  # 메시지도 삭제(cascade)
    assert store.delete_conversation("1", c.id) is False  # 이미 없음


def test_delete_others_conversation_forbidden(store):
    c = store.create_conversation("1")
    assert store.delete_conversation("2", c.id) is False  # 남의 대화 삭제 불가
    assert store.get_conversation("1", c.id) is not None  # 그대로


def test_user_isolation(store):
    c1 = store.create_conversation("1", title="A")
    store.create_conversation("2", title="B")
    convs1 = store.list_conversations("1")
    assert [c.title for c in convs1] == ["A"]  # 유저 1 은 자기 대화만
