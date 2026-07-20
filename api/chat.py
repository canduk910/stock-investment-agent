"""챗봇 라우터 — POST /api/chat (논스트림) + POST /api/chat/stream (SSE). 판정은 코드, LLM은 설명만.

논스트림(/api/chat): session_id 로 서버 세션 조회/생성 → live_judgement()로 최신 국면 계산
(캐시 미경유, 원칙1) → chat(message, judgement, session) → {text, popups} 반환. 스트리밍
미지원 환경의 폴백 겸 기존 계약(270 테스트) 유지.

스트리밍(/api/chat/stream): 같은 흐름을 SSE(text/event-stream)로 흘린다 — 진행 단계 이벤트
(analyze→regime→generate→summarize) + CHAT_MODEL 답변 토큰 실시간. 안전 원칙 동일:
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

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth.deps import get_current_user, get_current_user_optional
from auth.models import User
from auth.usage import consume, is_over_limit, quota_snapshot
from chat.chat import chat, chat_stream
from chat.history_store import HistoryStore
from chat.intent import guardrail_label
from chat.session import get_session
from infra.db import get_db

router = APIRouter()

# LLM 컨텍스트 hydrate 창(세션 슬라이딩 윈도우와 정합).
_HYDRATE_WINDOW = 8


def _limit_message(user: User) -> str:
    """토큰(질문) 한도 초과 시 안내(챗 텍스트로 표시). LLM 미호출 — 판정·차단은 코드."""
    limit = quota_snapshot(user)["daily_limit"]
    return (
        f"오늘 사용할 수 있는 질문 {limit}회를 모두 사용했습니다. "
        "질문 한도는 매일 자정(KST)에 초기화됩니다. 더 필요하면 관리자에게 한도 조정을 요청하세요."
    )


class ChatRequest(BaseModel):
    session_id: str  # = conversation.id(문자열). 프론트가 대화 생성 후 그 id 로 이어간다.
    message: str


def _conversation_id(user: User, db: Session, session_id: str) -> int | None:
    """session_id(=conversation.id) → 소유 대화 id. 남의 것/미존재/비정수는 None(기록 skip)."""
    try:
        conv_id = int(session_id)
    except (ValueError, TypeError):
        return None
    conv = HistoryStore(db).get_conversation(str(user.id), conv_id)
    return conv.id if conv is not None else None


def _hydrate_session(session, user: User, db: Session, session_id: str) -> None:
    """세션 히스토리가 비어 있으면 DB 대화기록으로 복원(재접속·전환·재시작 시 LLM 컨텍스트). best-effort."""
    try:
        if session.history():
            return  # 이미 인메모리 히스토리 있음(현재 서버 run 내 진행 중)
        conv_id = _conversation_id(user, db, session_id)
        if conv_id is not None:
            session.hydrate(HistoryStore(db).recent_messages(conv_id, _HYDRATE_WINDOW))
    except Exception:
        pass  # hydrate 실패는 챗을 막지 않는다(빈 컨텍스트로 진행)


def _persist_turn(user: User, db: Session, session_id: str, user_text: str, assistant_text: str) -> None:
    """user+assistant 한 턴을 대화기록에 저장(write-through, best-effort). 소유 대화만."""
    try:
        conv_id = _conversation_id(user, db, session_id)
        if conv_id is not None:
            HistoryStore(db).add_turn(conv_id, user_text, assistant_text)
    except Exception:
        pass  # 기록 실패는 챗 응답을 막지 않는다


class ReportContextRequest(BaseModel):
    session_id: str
    ticker: str | None = None
    report_id: str | None = None  # None → 컨텍스트 해제(상담 종료)


class ViewContextRequest(BaseModel):
    session_id: str
    kind: str | None = None  # None/비데이터 kind → 핀 해제
    args: dict = {}


class MarketOutlookContextRequest(BaseModel):
    session_id: str
    report_id: str | None = None  # None → 컨텍스트 해제(시황은 시장 전체라 ticker 없음)


@router.post("/api/chat")
def post_chat(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """{session_id(=conversation.id), message} → {text, popups}. 대화기록 DB 저장(유저 스코프)."""
    from api.main import live_judgement  # 지연 import(순환 참조 회피)

    # 토큰(질문) 한도 선차단 — 관리자 무제한, 초과면 LLM 미호출(비용·판정 코드가 결정).
    if is_over_limit(user):
        return {"text": _limit_message(user), "popups": []}

    session = get_session(body.session_id)
    _hydrate_session(session, user, db, body.session_id)
    judgement, _indicators_used, _partial_failure = live_judgement()
    result = chat(body.message, judgement, session)
    consume(user, db)  # 성공 턴 1회 소비 기록(일별 리셋 반영·누적·커밋)
    _persist_turn(user, db, body.session_id, body.message, result.get("text", ""))
    return result


@router.post("/api/chat/report-context")
def post_report_context(body: ReportContextRequest) -> dict:
    """저장된 애널리스트 리포트 요약을 세션 상담 컨텍스트로 핀 고정(또는 해제).

    body {session_id, ticker, report_id}. report_id/ticker 가 없으면 컨텍스트 해제.
    **요약 본문은 프론트가 보내지 않는다** — 서버가 store 에서 조회한 entry 로 컨텍스트를
    만든다(환각·조작 차단). 없는 리포트면 404. 데이터 자체는 반환하지 않고 세팅 결과만.
    """
    from fastapi import HTTPException

    from chat.analyst_report import format_report_context
    from chat.analyst_store import default_store
    from api.deps import assert_valid_ticker

    session = get_session(body.session_id)

    if not body.ticker or not body.report_id:
        session.clear_report_context()  # 상담 종료(해제)
        return {"ok": True, "set": False}

    assert_valid_ticker(body.ticker)
    entry = default_store().get(body.ticker, body.report_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="report not found")
    session.set_report_context(format_report_context(entry))
    return {
        "ok": True,
        "set": True,
        "broker": (entry.get("summary") or {}).get("증권사") or entry.get("broker", ""),
    }


@router.post("/api/chat/market-outlook-context")
def post_market_outlook_context(body: MarketOutlookContextRequest) -> dict:
    """저장된 **시황(매크로) 리포트** 요약을 세션 상담 컨텍스트로 핀(또는 해제).

    애널리스트 report-context 와 동일 메커니즘(같은 세션 핀 슬롯) — 시황은 **시장 전체**라 ticker 가
    없고 report_id 만 받는다. report_id 없으면 해제. **요약 본문은 프론트가 안 보낸다** — 서버가
    store 에서 조회한 entry 로 컨텍스트를 만든다(환각·조작 차단). 없는 리포트면 404.
    """
    from fastapi import HTTPException

    from chat.market_outlook import format_market_outlook_context
    from chat.market_outlook_store import default_store as outlook_store

    session = get_session(body.session_id)

    if not body.report_id:
        session.clear_report_context()  # 상담 종료(해제)
        return {"ok": True, "set": False}

    entry = outlook_store().get(body.report_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="market outlook not found")
    session.set_report_context(format_market_outlook_context(entry))
    return {
        "ok": True,
        "set": True,
        "broker": (entry.get("summary") or {}).get("증권사") or entry.get("broker", ""),
    }


@router.post("/api/chat/context")
def post_view_context(
    body: ViewContextRequest,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> dict:
    """사용자가 현재 보고 있는 화면(잔고·관심종목·종목상세)을 세션 핀 컨텍스트로 고정(또는 해제).

    body {session_id, kind, args}. 데이터 보유 kind 만 서버가 재조회해 스냅샷을 세팅한다
    (**요약 본문은 프론트가 보내지 않음** — 서버가 조회, 환각/조작 차단). 비데이터 kind·조회 불가는
    이전 핀을 해제. **항상 200**(백그라운드 핀은 게이트키핑 아님, graceful).
    """
    from chat.view_context import DATA_BEARING_KINDS, build_view_context

    session = get_session(body.session_id)

    if not body.kind or body.kind not in DATA_BEARING_KINDS:
        session.clear_view_context()  # 비데이터 화면(국면·관리)으로 전환 → 이전 스냅샷 제거
        return {"ok": True, "set": False}

    text = build_view_context(body.kind, body.args or {}, user=user, db=db)
    if text is None:  # 조회 불가·불량 인자 → 해제(graceful)
        session.clear_view_context()
        return {"ok": True, "set": False}
    session.set_view_context(text)
    return {"ok": True, "set": True, "kind": body.kind}


def _sse(body: ChatRequest, user: User, db: Session):
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
    _hydrate_session(session, user, db, body.session_id)

    yield frame({"type": "stage", "stage": "analyze"})

    # 토큰(질문) 한도 선차단 — 초과면 안내문만 토큰으로 흘리고 종료(chat_stream·LLM 미호출).
    if is_over_limit(user):
        yield frame({"type": "token", "text": _limit_message(user)})
        yield frame({"type": "done", "popups": []})
        return

    if guardrail_label(body.message):
        # 결정적 키워드 차단은 확정 → 국면 조회 불필요(live_judgement 미실행, FRED 낭비 0).
        # ML-risk 는 chat_stream 의 LLM 재분류로 허용될 수 있어 여기서 스킵하지 않는다(judgement 필요).
        judgement: dict = {}
    else:
        judgement, _used, _pf = live_judgement()
        yield frame({"type": "stage", "stage": "regime"})

    assistant_text = ""  # 토큰 누적 → 스트림 종료 후 대화기록 저장(write-through).
    for ev in chat_stream(body.message, judgement, session):
        # chat_stream 이 선두에 내는 analyze 는 라우트가 이미 냈으므로 중복 제거.
        if ev.get("type") == "stage" and ev.get("stage") == "analyze":
            continue
        if ev.get("type") == "token":
            assistant_text += ev.get("text", "")
        yield frame(ev)

    consume(user, db)  # 스트림 완료 후 1회 소비 기록(일별 리셋 반영·누적·커밋)
    _persist_turn(user, db, body.session_id, body.message, assistant_text)


@router.post("/api/chat/stream")
def post_chat_stream(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """{session_id, message} → SSE(text/event-stream) 진행 단계 + 답변 토큰 스트림.

    헤더로 프록시·브라우저 버퍼링을 막아(Cache-Control:no-cache, X-Accel-Buffering:no)
    토큰이 도착 즉시 흐르게 한다. 논스트림 /api/chat 은 폴백으로 그대로 유지. 대화기록은 스트림
    종료 후 write-through(유저 스코프). db Session 은 스트리밍 종료까지 살아 있다(get_db finally).
    """
    return StreamingResponse(
        _sse(body, user, db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
