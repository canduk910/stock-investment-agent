"""대화기록 저장소 — 유저별 대화 CRUD + 메시지 append/조회(요청 스코프 Session).

모든 조회는 user_id 스코프(유저 격리). 대화 소유권은 (user_id, conversation_id)로 검증한다.
recent_messages 는 LLM 컨텍스트 복원(재접속·재시작 시 슬라이딩 윈도우 hydrate)에 쓴다.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from chat.history_models import ChatMessage, Conversation


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HistoryStore:
    def __init__(self, db: Session) -> None:
        self._db = db

    # ── 대화 ─────────────────────────────────────────────────────────────────
    def create_conversation(self, user_id: str, title: str = "새 대화") -> Conversation:
        conv = Conversation(user_id=user_id, title=title)
        self._db.add(conv)
        self._db.commit()
        self._db.refresh(conv)
        return conv

    def list_conversations(self, user_id: str) -> list[Conversation]:
        """유저 대화 목록(최근 갱신순)."""
        return list(
            self._db.scalars(
                select(Conversation)
                .where(Conversation.user_id == user_id)
                .order_by(Conversation.updated_at.desc())
            ).all()
        )

    def get_conversation(self, user_id: str, conversation_id: int) -> Conversation | None:
        """소유권 검증 포함 조회 — 남의 대화면 None."""
        return self._db.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id, Conversation.user_id == user_id
            )
        )

    def delete_conversation(self, user_id: str, conversation_id: int) -> bool:
        conv = self.get_conversation(user_id, conversation_id)
        if conv is None:
            return False
        self._db.delete(conv)  # cascade 로 메시지도 삭제
        self._db.commit()
        return True

    # ── 메시지 ────────────────────────────────────────────────────────────────
    def add_message(self, conversation_id: int, role: str, content: str) -> ChatMessage:
        now = _utcnow()  # 명시 타임스탬프(flush 전 default 미적용 → conv.updated_at NULL 방지)
        msg = ChatMessage(
            conversation_id=conversation_id, role=role, content=content, created_at=now
        )
        self._db.add(msg)
        # 대화 updated_at 갱신(목록 정렬용).
        conv = self._db.get(Conversation, conversation_id)
        if conv is not None:
            conv.updated_at = now
        self._db.commit()
        self._db.refresh(msg)
        return msg

    def add_turn(self, conversation_id: int, user_text: str, assistant_text: str) -> None:
        """user+assistant 한 턴을 저장(챗 write-through)."""
        self.add_message(conversation_id, "user", user_text)
        self.add_message(conversation_id, "assistant", assistant_text)

    def list_messages(self, conversation_id: int) -> list[ChatMessage]:
        """대화 전체 메시지(시간순) — 히스토리 UI 로드용."""
        return list(
            self._db.scalars(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conversation_id)
                .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
            ).all()
        )

    def recent_messages(self, conversation_id: int, limit: int) -> list[dict]:
        """최근 limit 개 메시지를 {role, content} 시간순으로 — 세션 hydrate(LLM 컨텍스트)용."""
        rows = self._db.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(limit)
        ).all()
        return [{"role": m.role, "content": m.content} for m in reversed(rows)]
