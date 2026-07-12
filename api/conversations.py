"""대화(conversation) 라우터 — 유저별 대화 목록·생성·메시지 조회·삭제.

모두 get_current_user 스코프(유저 격리, 소유권 검증). session_id(챗)는 conversation.id 를 쓴다:
프론트가 POST /api/conversations 로 새 대화를 만들고 그 id 로 챗을 이어간다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.deps import get_current_user
from auth.models import User
from chat.history_models import DEFAULT_CONVERSATION_TITLE, Conversation, ChatMessage
from chat.history_store import HistoryStore
from infra.db import get_db

router = APIRouter()


class CreateConversationRequest(BaseModel):
    title: str | None = None


class RenameConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


def _conv_public(conv: Conversation) -> dict:
    return {
        "id": conv.id,
        "title": conv.title,
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
    }


def _msg_public(msg: ChatMessage) -> dict:
    return {"role": msg.role, "content": msg.content, "created_at": msg.created_at.isoformat()}


@router.get("/api/conversations")
def list_conversations(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    store = HistoryStore(db)
    return {"conversations": [_conv_public(c) for c in store.list_conversations(str(user.id))]}


@router.post("/api/conversations")
def create_conversation(
    body: CreateConversationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    store = HistoryStore(db)
    conv = store.create_conversation(str(user.id), title=(body.title or DEFAULT_CONVERSATION_TITLE))
    return _conv_public(conv)


@router.patch("/api/conversations/{conversation_id}")
def rename_conversation(
    conversation_id: int,
    body: RenameConversationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """대화 제목 변경(유저 소유권 검증). 빈 제목/초과는 422(Pydantic), 남의 대화는 404."""
    store = HistoryStore(db)
    conv = store.rename_conversation(str(user.id), conversation_id, body.title)
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return _conv_public(conv)


@router.get("/api/conversations/{conversation_id}/messages")
def get_messages(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    store = HistoryStore(db)
    conv = store.get_conversation(str(user.id), conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {
        "conversation": _conv_public(conv),
        "messages": [_msg_public(m) for m in store.list_messages(conversation_id)],
    }


@router.delete("/api/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    store = HistoryStore(db)
    if not store.delete_conversation(str(user.id), conversation_id):
        raise HTTPException(status_code=404, detail="conversation not found")
    return {"ok": True}
