"""서버 세션 저장 + 슬라이딩 윈도우 테스트 — 계획 §3, 골격 §3.

시스템 프롬프트는 매 호출 재주입(누적 X)이므로 세션은 user/assistant 만 담는다.
tool 메시지는 히스토리에 누적하지 않는다(다음 턴 토큰 낭비). 서버 스토어는
session_id 별 Session 을 메모리에 보관(SESSIONS dict).
"""
from __future__ import annotations

from chat.session import SESSIONS, Session, get_session


def test_new_session_has_empty_history():
    assert Session().history() == []


def test_append_stores_user_then_assistant_roles():
    s = Session()
    s.append("안녕", "안녕하세요")
    hist = s.history()
    assert hist == [
        {"role": "user", "content": "안녕"},
        {"role": "assistant", "content": "안녕하세요"},
    ]


def test_history_only_contains_user_and_assistant_roles():
    s = Session()
    for i in range(3):
        s.append(f"q{i}", f"a{i}")
    assert {m["role"] for m in s.history()} == {"user", "assistant"}


def test_sliding_window_truncates_to_last_window_messages():
    s = Session(window=4)  # 최근 4개 메시지(=2턴)만 유지
    for i in range(5):
        s.append(f"q{i}", f"a{i}")  # 10 messages appended
    hist = s.history()
    assert len(hist) == 4
    # 가장 오래된 것은 잘리고 최신 2턴만 남는다.
    assert hist[0]["content"] == "q3"
    assert hist[-1]["content"] == "a4"


def test_reset_clears_history():
    s = Session()
    s.append("q", "a")
    s.reset()
    assert s.history() == []


# ── 핀 리포트 컨텍스트(상담 연계, Phase D) ────────────────────────────────────


def test_report_context_default_none():
    assert Session().report_context is None


def test_set_and_clear_report_context():
    s = Session()
    s.set_report_context("리포트 요약 텍스트")
    assert s.report_context == "리포트 요약 텍스트"
    s.clear_report_context()
    assert s.report_context is None


def test_set_report_context_empty_clears():
    s = Session()
    s.set_report_context("x")
    s.set_report_context("")  # 빈 문자열 → 해제
    assert s.report_context is None


def test_report_context_survives_sliding_window():
    # 핀 컨텍스트는 슬라이딩 윈도우와 별개 — 여러 턴 뒤에도 유지된다.
    s = Session(window=2)
    s.set_report_context("리포트")
    for i in range(5):
        s.append(f"q{i}", f"a{i}")
    assert s.report_context == "리포트"


def test_reset_clears_report_context():
    s = Session()
    s.set_report_context("리포트")
    s.reset()
    assert s.report_context is None


# ── 핀 뷰 컨텍스트(현재 보고 있는 화면 스냅샷) ────────────────────────────────
# report_context 와 별개 슬롯 — 사용자가 보는 패널(잔고·관심종목·종목)을 대화에 반영.


def test_view_context_default_none():
    assert Session().view_context is None


def test_set_and_clear_view_context():
    s = Session()
    s.set_view_context("잔고 스냅샷")
    assert s.view_context == "잔고 스냅샷"
    s.clear_view_context()
    assert s.view_context is None


def test_set_view_context_empty_clears():
    s = Session()
    s.set_view_context("x")
    s.set_view_context("")  # 빈 문자열 → 해제
    assert s.view_context is None


def test_view_context_survives_sliding_window():
    # 핀 컨텍스트는 슬라이딩 윈도우와 별개 — 여러 턴 뒤에도 유지된다.
    s = Session(window=2)
    s.set_view_context("잔고")
    for i in range(5):
        s.append(f"q{i}", f"a{i}")
    assert s.view_context == "잔고"


def test_view_and_report_context_independent():
    # 두 핀 슬롯은 서로 간섭하지 않는다(공존).
    s = Session()
    s.set_report_context("리포트")
    s.set_view_context("잔고")
    assert s.report_context == "리포트" and s.view_context == "잔고"
    s.clear_view_context()
    assert s.report_context == "리포트" and s.view_context is None


def test_reset_clears_view_context():
    s = Session()
    s.set_view_context("잔고")
    s.reset()
    assert s.view_context is None


# ── 서버 세션 스토어 (SESSIONS dict) ─────────────────────────────────────────


def test_get_session_creates_new_for_unknown_id():
    SESSIONS.clear()
    s = get_session("sid-1", owner="u1")
    assert isinstance(s, Session)
    assert s.history() == []


def test_get_session_returns_same_instance_for_same_owner_and_id():
    SESSIONS.clear()
    s1 = get_session("sid-2", owner="u1")
    s1.append("q", "a")
    s2 = get_session("sid-2", owner="u1")
    assert s1 is s2
    assert len(s2.history()) == 2  # 같은 (owner,id) 재사용 시 히스토리 누적


def test_get_session_isolates_different_ids():
    SESSIONS.clear()
    get_session("a", owner="u1").append("qa", "aa")
    b = get_session("b", owner="u1")
    assert b.history() == []  # 신규 id 는 빈 히스토리(격리)


def test_get_session_requires_owner_keyword():
    # owner 는 keyword-only·기본값 없음 — 소유권 없이 세션을 꺼낼 수 없다(safe-by-construction).
    import pytest

    with pytest.raises(TypeError):
        get_session("sid")  # type: ignore[call-arg]


# ── 크로스유저(IDOR) 격리 — 같은 session_id 라도 owner 가 다르면 완전 격리 ──────────
# session_id 는 conversation.id(순차 정수)라 유저 B 가 유저 A 의 id 를 보낼 수 있다. owner 스코프가
# 없으면 B 가 A 의 핀(잔고·상담 리포트 스냅샷)·히스토리에 접근한다(취약점). 아래가 그 회귀 잠금.


def test_same_session_id_different_owners_are_isolated():
    SESSIONS.clear()
    a = get_session("42", owner="A")
    a.set_report_context("A 의 애널리스트 리포트 상담 컨텍스트")
    a.set_view_context("A 의 잔고 스냅샷")
    a.append("A 질문", "A 답변")

    # 유저 B 가 같은 session_id("42")로 세션을 꺼내도 A 의 세션이 아닌 새 세션을 받는다.
    b = get_session("42", owner="B")
    assert b is not a
    assert b.report_context is None  # A 의 상담 컨텍스트가 새지 않음
    assert b.view_context is None    # A 의 화면 스냅샷이 새지 않음
    assert b.history() == []         # A 의 대화 히스토리가 새지 않음


def test_same_owner_and_id_shares_session_across_pin_and_turn():
    # 정상 기능 보존: 같은 유저가 핀 엔드포인트와 챗 턴에서 같은 session_id 를 쓰면 같은 세션을 공유.
    SESSIONS.clear()
    pinned = get_session("7", owner="A")
    pinned.set_report_context("A 리포트")
    # 이후 챗 턴이 같은 (owner, id) 로 세션을 꺼내면 방금 건 핀이 살아 있어야 한다.
    turn = get_session("7", owner="A")
    assert turn is pinned
    assert turn.report_context == "A 리포트"
