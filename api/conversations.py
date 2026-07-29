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
    # title 미지정(None)이면 create 라우트가 DEFAULT_CONVERSATION_TITLE("새 대화")로 채운다.
    # 첫 질문이 오면 history_store 가 그 제목을 첫 user_text 로 자동 명명(요약 LLM 아님·비용 0).
    title: str | None = None


class RenameConversationRequest(BaseModel):
    # 수동 제목 편집용 — 빈 문자열/200자 초과는 Pydantic 이 422 로 거른다(라우트 진입 전).
    title: str = Field(min_length=1, max_length=200)


def _conv_public(conv: Conversation) -> dict:
    """Conversation ORM → 프론트 응답 dict(계약 SSOT). datetime 은 ISO 문자열로 직렬화."""
    return {
        "id": conv.id,
        "title": conv.title,
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
    }


def _msg_public(msg: ChatMessage) -> dict:
    """ChatMessage ORM → 프론트 응답 dict. role 은 'user'|'assistant'(hydrate 시 재구성 원천)."""
    return {"role": msg.role, "content": msg.content, "created_at": msg.created_at.isoformat()}


@router.get("/api/conversations")
def list_conversations(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    """로그인 유저의 대화 목록(최신순). get_current_user 스코프라 남의 대화는 애초에 안 나온다."""
    store = HistoryStore(db)
    # user.id 는 int → str 로 통일해 store user_id 로 사용(전 유저별 store 계약이 문자열 키).
    return {"conversations": [_conv_public(c) for c in store.list_conversations(str(user.id))]}


@router.post("/api/conversations")
def create_conversation(
    body: CreateConversationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """새 대화 생성 → 그 conversation.id 가 이후 챗의 session_id 가 된다(프론트가 이 id 로 챗 진행)."""
    store = HistoryStore(db)
    # 제목 미지정이면 기본 제목("새 대화") — 첫 질문 시 자동 명명으로 교체된다.
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
    # rename_conversation 이 소유권을 검증한다 — 남의 대화이거나 없으면 None → 404(존재 여부 은닉).
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
    """대화 하나의 메시지 전체(재접속·대화 전환 시 챗 화면 복원용). 소유권 없으면 404."""
    store = HistoryStore(db)
    # 먼저 소유권 확인(get_conversation 이 user 스코프) — 통과해야 메시지를 노출한다.
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
    """대화 삭제(메시지는 relationship cascade 로 함께). 남의 대화/없음은 404(delete 가 False 반환)."""
    store = HistoryStore(db)
    if not store.delete_conversation(str(user.id), conversation_id):
        raise HTTPException(status_code=404, detail="conversation not found")
    return {"ok": True}
