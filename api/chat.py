"""챗봇 라우터 — POST /api/chat (논스트림) + POST /api/chat/stream (SSE). 판정은 코드, LLM은 설명만.

논스트림(/api/chat): session_id 로 서버 세션 조회/생성 → live_judgement()로 최신 국면 계산
(캐시 미경유, 원칙1) → chat(message, judgement, session) → {text, popups} 반환. 스트리밍
미지원 환경의 폴백 겸 기존 계약(270 테스트) 유지.

스트리밍(/api/chat/stream): 같은 흐름을 SSE(text/event-stream)로 흘린다 — 진행 단계 이벤트
(analyze→regime→generate→summarize) + gpt-5.4 답변 토큰 실시간. 안전 원칙 동일:
risk_guardrail 은 코드가 결정적으로 차단(LLM 미호출), 팝업은 tool_calls 에서만, 판정 숫자는 코드.

live judgement 계산은 api.main.live_judgement 를 재사용한다(핸들러 내부 지연 import 로
순환 참조 회피 — main 이 이 라우터를 include 하기 때문).

SSE 이벤트 계약(frontend·QA 단일 출처):
  stage enum = analyze | regime | generate | summarize
  {"type":"stage","stage":<enum>}
  {"type":"token","text":<델타>}
  {"type":"popups","popups":[{"name","args"}]}
  {"type":"done","popups":[...]}
guardrail 경로는 chat_stream 이 generate 를 내지 않으므로 regime 단계도 주입되지 않는다
(국면 조회 불필요 → live_judgement 미실행, FRED 낭비 없음).
"""
from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from chat.chat import chat, chat_stream
from chat.intent import classify
from chat.session import get_session

router = APIRouter()


class ChatRequest(BaseModel):
    session_id: str
    message: str


@router.post("/api/chat")
def post_chat(body: ChatRequest) -> dict:
    """{session_id, message} → {text, popups}. 서버가 session_id 별 히스토리 보관."""
    from api.main import live_judgement  # 지연 import(순환 참조 회피)

    session = get_session(body.session_id)
    judgement, _indicators_used, _partial_failure = live_judgement()
    return chat(body.message, judgement, session)


def _sse(body: ChatRequest):
    """동기 제너레이터: 진행 단계·토큰을 `data: {json}\n\n` SSE 프레임으로 흘린다.

    흐름 조립:
    1. stage:analyze 를 먼저 낸다.
    2. classify 로 guardrail 을 판정한다(라우트가 국면 조회 낭비 여부를 결정).
       - guardrail 이면 국면 조회 없이 chat_stream 으로 차단문만 흘린다(regime 미주입).
       - 아니면 live_judgement()를 이 자리에서 실행(‘시장 국면 조회’ 타이밍이 실제 FRED
         조회와 일치) → stage:regime 주입 → chat_stream(judgement) 호출.
    3. chat_stream 은 자체적으로 analyze 를 선두에 내므로(guardrail 이중 방어), 여기선 그
       중복 analyze 이벤트를 스킵하고 나머지 이벤트만 통과시킨다.
    """
    from api.main import live_judgement  # 지연 import(순환 참조 회피)

    def frame(ev: dict) -> str:
        return f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    session = get_session(body.session_id)

    yield frame({"type": "stage", "stage": "analyze"})

    if classify(body.message) == "risk_guardrail":
        # guardrail: 국면 조회 불필요 → live_judgement 미실행. chat_stream 이 결정적 차단.
        judgement: dict = {}
    else:
        judgement, _used, _pf = live_judgement()
        yield frame({"type": "stage", "stage": "regime"})

    for ev in chat_stream(body.message, judgement, session):
        # chat_stream 이 선두에 내는 analyze 는 라우트가 이미 냈으므로 중복 제거.
        if ev.get("type") == "stage" and ev.get("stage") == "analyze":
            continue
        yield frame(ev)


@router.post("/api/chat/stream")
def post_chat_stream(body: ChatRequest) -> StreamingResponse:
    """{session_id, message} → SSE(text/event-stream) 진행 단계 + 답변 토큰 스트림.

    헤더로 프록시·브라우저 버퍼링을 막아(Cache-Control:no-cache, X-Accel-Buffering:no)
    토큰이 도착 즉시 흐르게 한다. 논스트림 /api/chat 은 폴백으로 그대로 유지.
    """
    return StreamingResponse(
        _sse(body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
