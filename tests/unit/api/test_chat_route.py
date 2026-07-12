"""POST /api/chat 라우트 계약 테스트 — 계획 §6 (경계 mock, 실 LLM/키 불요).

chat.chat 과 collect_macro_indicators 를 경계로 mock 해 계약만 검증한다: 응답 shape
{text, popups}, session_id 전달, POST 메서드, judgement 를 live 계산해 chat 에 넘기는지.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api.main as main
from auth.deps import get_current_user
from collectors.base import indicator_point
from infra.db import get_db


@pytest.fixture(autouse=True)
def _auth_override():
    # 챗 라우트는 이제 인증 필수 + DB 대화기록 저장(유저 스코프). 고정 유저·더미 db 로 오버라이드
    # (db=None → 대화기록 helper 는 best-effort try/except 로 no-op). 후처리로 정리(누수 방지).
    main.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    main.app.dependency_overrides[get_db] = lambda: None
    yield
    main.app.dependency_overrides.pop(get_current_user, None)
    main.app.dependency_overrides.pop(get_db, None)


def _client(monkeypatch):
    monkeypatch.setattr(main, "fred_api_key", lambda: "KEY")
    return TestClient(main.app)


def _fake_snapshot(key):
    return {
        "indicators": {
            "t10y2y": indicator_point("T10Y2Y", 0.6, dt.date(2026, 7, 2), "FRED"),
            "hy_spread": indicator_point("HY", 2.0, dt.date(2026, 7, 2), "FRED"),
            "vix": indicator_point("VIX", 12.0, dt.date(2026, 7, 2), "FRED"),
            "fear_greed": None,
        },
        "partial_failure": ["fear_greed"],
    }


def test_post_chat_returns_text_and_popups_shape(monkeypatch):
    import api.chat as chat_route

    monkeypatch.setattr(main, "collect_macro_indicators", _fake_snapshot)
    captured = {}

    def fake_chat(message, judgement, session, **kwargs):
        captured["message"] = message
        captured["judgement"] = judgement
        return {"text": "설명입니다.", "popups": [{"name": "show_stock_report", "args": {"ticker": "005930"}}]}

    monkeypatch.setattr(chat_route, "chat", fake_chat)

    client = _client(monkeypatch)
    resp = client.post("/api/chat", json={"session_id": "s1", "message": "삼성전자 어때"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == "설명입니다."
    assert body["popups"][0]["name"] == "show_stock_report"
    # judgement 가 live 계산돼 chat 에 전달됐는지(엔진 계약의 regime 키 존재).
    assert "regime" in captured["judgement"]
    assert captured["message"] == "삼성전자 어때"


def test_post_chat_reuses_session_across_calls(monkeypatch):
    import api.chat as chat_route

    monkeypatch.setattr(main, "collect_macro_indicators", _fake_snapshot)
    seen_sessions = []

    def fake_chat(message, judgement, session, **kwargs):
        seen_sessions.append(id(session))
        return {"text": "ok", "popups": []}

    monkeypatch.setattr(chat_route, "chat", fake_chat)
    client = _client(monkeypatch)

    client.post("/api/chat", json={"session_id": "same", "message": "a"})
    client.post("/api/chat", json={"session_id": "same", "message": "b"})
    # 같은 session_id → 같은 Session 인스턴스(서버 세션 저장).
    assert seen_sessions[0] == seen_sessions[1]


def test_get_not_allowed_on_chat(monkeypatch):
    client = _client(monkeypatch)
    assert client.get("/api/chat").status_code == 405  # POST 전용
