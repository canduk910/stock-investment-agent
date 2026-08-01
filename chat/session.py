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
        # 사용자가 '현재 보고 있는 화면'(잔고·관심종목·종목상세) 스냅샷 핀 — report_context 와 별개.
        # 패널을 열면 서버가 조회한 스냅샷을 실어 후속 질문이 그 화면 데이터를 근거로 답하게 한다.
        self.view_context: str | None = None

    def history(self) -> list[dict]:
        """최근 window 개 메시지만 반환(시스템·tool 미포함)."""
        return self._msgs[-self.window :]

    def append(self, user: str, assistant: str) -> None:
        self._msgs += [
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]

    def hydrate(self, msgs: list[dict]) -> None:
        """DB 대화기록으로 히스토리를 복원(재접속·재시작·대화 전환 시 LLM 컨텍스트 회복).

        msgs 는 {role, content} 시간순 리스트(user/assistant). 핀(report/view_context)은 건드리지
        않는다 — 슬라이딩 윈도우 히스토리만 교체(DB 가 source of truth).
        """
        self._msgs = list(msgs)

    def set_report_context(self, text: str | None) -> None:
        """리포트 요약 텍스트를 핀 컨텍스트로 설정(None/빈문자열이면 해제)."""
        self.report_context = text or None

    def clear_report_context(self) -> None:
        self.report_context = None

    def set_view_context(self, text: str | None) -> None:
        """현재 보는 화면 스냅샷을 핀으로 설정(None/빈문자열이면 해제)."""
        self.view_context = text or None

    def clear_view_context(self) -> None:
        self.view_context = None

    def reset(self) -> None:
        self._msgs = []
        self.report_context = None
        self.view_context = None


# 서버 세션 스토어(인메모리) — "{owner}:{session_id}" → Session.
# 키를 owner(=인증 유저 id) 로 스코프해 크로스유저 재사용을 원천 차단한다(아래 get_session 참고).
SESSIONS: dict[str, Session] = {}


def get_session(session_id: str, *, owner: str) -> Session:
    """(owner, session_id) 로 세션 조회, 없으면 생성해 등록. **owner 필수(safe-by-construction)**.

    보안(크로스유저/IDOR 차단): session_id 는 conversation.id(순차 정수)라 유저 B 가 body 에
    유저 A 의 session_id 를 실어 보내면 A 의 핀(잔고·보유종목·상담 리포트 스냅샷·히스토리)이 B 의
    답변에 새어나갈 수 있었다. 내부 키를 f"{owner}:{session_id}" 로 구성하면 B 의 요청은 키가
    "B:{id}" 가 되어 A 의 세션("A:{id}")에 **절대 도달하지 못한다**. owner 없이는 호출 불가
    (keyword-only·기본값 없음) — 소유권 게이트를 잊고 세션을 꺼낼 수 없게 강제한다.

    같은 유저의 핀 엔드포인트(report-context·context)와 챗 턴은 같은 (owner, session_id) 라
    동일 scoped 세션을 공유 → 정상 기능(상담하기·현재화면 컨텍스트·P2 되먹임)은 그대로 동작한다.
    """
    key = f"{owner}:{session_id}"
    session = SESSIONS.get(key)
    if session is None:
        session = Session()
        SESSIONS[key] = session
    return session
