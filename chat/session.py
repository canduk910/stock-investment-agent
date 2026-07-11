"""서버 세션 저장 + 슬라이딩 윈도우 — 계획 §3, llm-agent-patterns §3.

세션은 대화 히스토리(user/assistant)만 담는다. 시스템 프롬프트는 chat()이 매 호출
최신 judgement 로 재주입하므로 여기에 누적하지 않는다(국면 변경 자동 반영). tool 메시지도
누적하지 않는다(다음 턴 토큰 낭비 — 팝업 지시는 그 턴 한정).

서버 스토어: 모듈 레벨 SESSIONS[session_id] → Session. 프론트는 session_id 만 보내고,
백엔드가 세션 상태를 보관한다(사용자 결정: 서버 세션 저장). 데모용 인메모리 —
클라우드 전환 시 DynamoDB/Redis 로 교체하는 것이 계약 경계다.
"""
from __future__ import annotations


class Session:
    """슬라이딩 윈도우 대화 히스토리(user/assistant 만) + 핀 리포트 컨텍스트."""

    def __init__(self, window: int = 8) -> None:
        self._msgs: list[dict] = []
        self.window = window
        # 애널리스트 리포트 요약을 '상담 컨텍스트'로 핀 고정 — 슬라이딩 윈도우와 별개로 유지돼
        # 후속 여러 턴에서 참조된다(사용자가 리포트를 근거로 이어서 자문). None 이면 미설정.
        self.report_context: str | None = None

    def history(self) -> list[dict]:
        """최근 window 개 메시지만 반환(시스템·tool 미포함)."""
        return self._msgs[-self.window :]

    def append(self, user: str, assistant: str) -> None:
        self._msgs += [
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]

    def set_report_context(self, text: str | None) -> None:
        """리포트 요약 텍스트를 핀 컨텍스트로 설정(None/빈문자열이면 해제)."""
        self.report_context = text or None

    def clear_report_context(self) -> None:
        self.report_context = None

    def reset(self) -> None:
        self._msgs = []
        self.report_context = None


# 서버 세션 스토어(인메모리) — session_id → Session.
SESSIONS: dict[str, Session] = {}


def get_session(session_id: str) -> Session:
    """session_id 로 세션 조회, 없으면 생성해 등록."""
    session = SESSIONS.get(session_id)
    if session is None:
        session = Session()
        SESSIONS[session_id] = session
    return session
