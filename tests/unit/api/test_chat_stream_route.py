"""POST /api/chat/stream SSE 라우트 계약 테스트 — 계획 §백엔드(경계 mock).

chat_stream·live_judgement 를 경계로 mock 해 SSE 계약만 검증한다:
- media_type text/event-stream, no-buffering 헤더
- 본문이 `data: {json}\n\n` 라인으로 흐르고, 이벤트 순서(analyze→regime→generate→…→done)
- live_judgement 가 제너레이터 안(regime 단계)에서 실행돼 chat_stream 에 judgement 전달
- guardrail(chat_stream 이 generate 를 안 냄) → regime 단계 미주입, LLM 미호출 흐름 유지
기존 test_chat_route.py(논스트림) 계약은 불변.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api.chat as chat_route
import api.main as main
from auth.deps import get_current_user
from infra.db import get_db


@pytest.fixture(autouse=True)
def _auth_override():
    # 챗 스트림 라우트도 인증 필수 + 대화기록 저장 + 토큰 한도 enforcement. 한도 여유 있는 고정 유저 +
    # commit 가능한 더미 db(대화기록 helper 는 no-op, consume 는 db.commit()).
    from auth.usage import today_kst

    user = SimpleNamespace(
        id=1, is_admin=False, daily_limit=20, used_today=0, usage_date=today_kst(), total_questions=0
    )
    fake_db = SimpleNamespace(commit=lambda: None)
    main.app.dependency_overrides[get_current_user] = lambda: user
    main.app.dependency_overrides[get_db] = lambda: fake_db
    yield
    main.app.dependency_overrides.pop(get_current_user, None)
    main.app.dependency_overrides.pop(get_db, None)


def _parse_sse(text: str) -> list[dict]:
    """SSE 본문에서 `data: ` 라인의 JSON 이벤트를 순서대로 파싱."""
    events = []
    for line in text.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:") :].strip()))
    return events


def test_stream_normal_flow_orders_stages_and_forwards_judgement(monkeypatch):
    captured = {}

    def fake_live_judgement():
        captured["called"] = True
        return ({"regime": "안정적_확장"}, {}, [])

    def fake_chat_stream(message, judgement, session, **kwargs):
        captured["message"] = message
        captured["judgement"] = judgement
        yield {"type": "stage", "stage": "analyze"}
        yield {"type": "stage", "stage": "generate"}
        yield {"type": "token", "text": "답변"}
        yield {"type": "done", "popups": []}

    monkeypatch.setattr(main, "live_judgement", fake_live_judgement)
    monkeypatch.setattr(chat_route, "chat_stream", fake_chat_stream)

    client = TestClient(main.app)
    with client.stream("POST", "/api/chat/stream", json={"session_id": "s1", "message": "삼성전자 어때"}) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert resp.headers.get("cache-control") == "no-cache"
        assert resp.headers.get("x-accel-buffering") == "no"
        body = resp.read().decode()

    events = _parse_sse(body)
    stages = [e["stage"] for e in events if e["type"] == "stage"]
    # regime 이 analyze 와 generate 사이에 주입됨(FRED 조회 타이밍 일치).
    assert stages == ["analyze", "regime", "generate"]
    assert captured["called"] is True
    assert captured["judgement"] == {"regime": "안정적_확장"}
    assert captured["message"] == "삼성전자 어때"
    assert events[-1] == {"type": "done", "popups": []}


def test_stream_guardrail_skips_regime_stage(monkeypatch):
    """guardrail 이면 chat_stream 이 generate 를 안 내므로 regime 단계도 주입되지 않는다."""
    calls = {"live": 0}

    def fake_live_judgement():
        calls["live"] += 1
        return ({"regime": "x"}, {}, [])

    def fake_chat_stream(message, judgement, session, **kwargs):
        # guardrail 경로: analyze 후 바로 차단 token → done (generate 없음)
        yield {"type": "stage", "stage": "analyze"}
        yield {"type": "token", "text": "차단 안내"}
        yield {"type": "done", "popups": []}

    monkeypatch.setattr(main, "live_judgement", fake_live_judgement)
    monkeypatch.setattr(chat_route, "chat_stream", fake_chat_stream)

    client = TestClient(main.app)
    with client.stream("POST", "/api/chat/stream", json={"session_id": "g", "message": "빚내서 몰빵"}) as resp:
        body = resp.read().decode()

    events = _parse_sse(body)
    stages = [e["stage"] for e in events if e["type"] == "stage"]
    assert "regime" not in stages
    # guardrail 은 국면 조회가 불필요 → live_judgement 미실행(관찰 가능한 낭비 없음).
    assert calls["live"] == 0
    assert events[-1] == {"type": "done", "popups": []}


def test_stream_ml_risk_without_keyword_still_fetches_judgement(monkeypatch):
    """결정적 키워드 없는 질의는 라우트가 국면을 조회한다 — chat_stream 의 LLM 재분류로
    허용될 수 있어 judgement(국면)가 필요하기 때문(결정적 차단만 스킵)."""
    calls = {"live": 0}

    def fake_live_judgement():
        calls["live"] += 1
        return ({"regime": "확장"}, {}, [])

    def fake_chat_stream(message, judgement, session, **kwargs):
        yield {"type": "stage", "stage": "generate"}
        yield {"type": "token", "text": "답변"}
        yield {"type": "done", "popups": []}

    monkeypatch.setattr(main, "live_judgement", fake_live_judgement)
    monkeypatch.setattr(chat_route, "chat_stream", fake_chat_stream)

    client = TestClient(main.app)
    # 키워드 없는 질의(결정적 차단 아님) → judgement 조회돼야 한다.
    with client.stream("POST", "/api/chat/stream", json={"session_id": "m", "message": "이 종목 결국 오르지?"}) as resp:
        body = resp.read().decode()

    events = _parse_sse(body)
    stages = [e["stage"] for e in events if e["type"] == "stage"]
    assert "regime" in stages
    assert calls["live"] == 1  # 결정적 차단이 아니므로 국면 조회 실행


def test_stream_over_limit_blocks_without_calling_chat_stream(monkeypatch):
    """한도 초과 유저 → chat_stream·live_judgement 미호출, analyze 후 안내 token + done 만."""
    from auth.usage import today_kst

    over = SimpleNamespace(
        id=2, is_admin=False, daily_limit=20, used_today=20, usage_date=today_kst(), total_questions=20
    )
    main.app.dependency_overrides[get_current_user] = lambda: over
    calls = {"stream": 0, "live": 0}

    def fake_live_judgement():
        calls["live"] += 1
        return ({"regime": "x"}, {}, [])

    def fake_chat_stream(*a, **k):
        calls["stream"] += 1
        yield {"type": "done", "popups": []}

    monkeypatch.setattr(main, "live_judgement", fake_live_judgement)
    monkeypatch.setattr(chat_route, "chat_stream", fake_chat_stream)

    client = TestClient(main.app)
    with client.stream("POST", "/api/chat/stream", json={"session_id": "s1", "message": "삼성전자 어때"}) as resp:
        assert resp.status_code == 200
        body = resp.read().decode()

    events = _parse_sse(body)
    tokens = "".join(e.get("text", "") for e in events if e["type"] == "token")
    assert "한도" in tokens  # 안내문만 흘렀다
    assert events[-1] == {"type": "done", "popups": []}
    assert calls["stream"] == 0 and calls["live"] == 0  # LLM·국면 조회 미실행


def test_stream_reuses_session_across_calls(monkeypatch):
    seen = []

    def fake_live_judgement():
        return ({"regime": "x"}, {}, [])

    def fake_chat_stream(message, judgement, session, **kwargs):
        seen.append(id(session))
        yield {"type": "stage", "stage": "analyze"}
        yield {"type": "stage", "stage": "generate"}
        yield {"type": "done", "popups": []}

    monkeypatch.setattr(main, "live_judgement", fake_live_judgement)
    monkeypatch.setattr(chat_route, "chat_stream", fake_chat_stream)

    client = TestClient(main.app)
    for _ in range(2):
        with client.stream("POST", "/api/chat/stream", json={"session_id": "same", "message": "a"}) as resp:
            resp.read()
    assert seen[0] == seen[1]
