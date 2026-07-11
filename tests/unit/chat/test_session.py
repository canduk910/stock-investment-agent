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


# ── 서버 세션 스토어 (SESSIONS dict) ─────────────────────────────────────────


def test_get_session_creates_new_for_unknown_id():
    SESSIONS.clear()
    s = get_session("sid-1")
    assert isinstance(s, Session)
    assert s.history() == []


def test_get_session_returns_same_instance_for_same_id():
    SESSIONS.clear()
    s1 = get_session("sid-2")
    s1.append("q", "a")
    s2 = get_session("sid-2")
    assert s1 is s2
    assert len(s2.history()) == 2  # 같은 id 재사용 시 히스토리 누적


def test_get_session_isolates_different_ids():
    SESSIONS.clear()
    get_session("a").append("qa", "aa")
    b = get_session("b")
    assert b.history() == []  # 신규 id 는 빈 히스토리(격리)
