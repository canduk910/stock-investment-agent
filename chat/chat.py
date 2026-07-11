"""챗봇 agent 루프 + 인텐트 통합 — 계획 §5, 골격 §1. LLM은 설명만.

흐름:
1. classify(user_query) — 결정적 가드레일 우선 ML 6분류(chat/intent.py).
   risk_guardrail 이면 **LLM 을 호출하지 않고** 코드가 정한 차단 안내를 반환한다
   (popups=[]). 차단은 코드가 결정한다(안전 원칙).
2. 그 외엔 CHAT_MODEL agent 루프: system=build_prompt(judgement)를 매 호출
   최신 주입 → tools=TOOLS, tool_choice="auto" → tool_calls 를 popups 로 추출(팝업 지시,
   데이터 아님) → tool 결과는 {"ok":True} 확인만 되먹이고(실데이터는 프론트가 조회) →
   최종 답변 text.
3. 반환 {"text", "popups":[{name,args}]} — frontend 계약(스킬 §2). 세션에 (user, text) append.

안전: OpenAI 호출 실패는 1회 재시도 후 폴백 텍스트("일시 응답 불가")로 크래시 없이 반환한다.
judgement·팝업 숫자는 코드/프론트가 확정 — LLM 은 재판정·숫자생성을 하지 않는다.
"""
from __future__ import annotations

import json

from chat.build_prompt import build_prompt
from chat.intent import classify
from chat.session import Session
from chat.tools import CHAT_MODEL, CHAT_MODEL_PARAMS, CONTENT_TOOLS, TOOLS, run_content_tool

# risk_guardrail 차단 안내(결정적). ③ 과도한 위험은 거절이 아니라 위험 환기 + 분산 안내로
# 방향 전환(스킬 §3). 단정 예측·내부정보·시세조종 요구도 이 안내로 일괄 차단한다.
_GUARDRAIL_MESSAGE = (
    "요청하신 내용은 도와드리기 어렵습니다. 저는 특정 종목이 '반드시/확실히 오른다'는 "
    "단정적 예측이나, 내부·미공개 정보, 시세조종, 빚을 내거나 한 종목에 몰아넣는 과도한 "
    "위험 감수를 권할 수 없습니다.\n\n"
    "투자에는 항상 손실 위험이 있습니다. 특정 종목·시점에 자산을 집중하기보다, 국면에 "
    "맞는 현금비중과 분산으로 위험을 관리하시길 권합니다. 시장 국면이나 개별 종목의 "
    "밸류에이션·리스크는 언제든 설명해 드리겠습니다.\n\n"
    "이 안내는 참고용이며, 면허 있는 투자자문이 아닙니다."
)

# OpenAI 전체 실패 시 폴백(크래시 금지).
_FALLBACK_MESSAGE = (
    "죄송합니다. 지금은 일시적으로 답변을 생성할 수 없습니다. 잠시 후 다시 시도해 주세요."
)


# 리포트 상담 컨텍스트 주입 블록(핀 고정). 출처 귀속·판정 금지·면책 유지를 재강조한다 —
# 필수 6블록·가드레일은 build_prompt 가 이미 강제하고, 이 블록은 '리포트 근거 자문'만 얹는다.
_REPORT_CONTEXT_HEADER = (
    "\n\n[사용자가 상담 컨텍스트로 불러온 애널리스트 리포트 요약]\n"
    "아래는 해당 증권사 애널리스트 리포트의 요약이다. 사용자의 후속 질문에 이 내용을 근거로 "
    "답하되, 반드시 '리포트에 따르면'처럼 **출처를 귀속**해 인용하고, 네 자신의 매수/매도 "
    "단정 판정은 하지 말며(리포트의 의견은 인용일 뿐), 면책 고지를 유지하라.\n"
)


# 현재 보고 있는 화면 스냅샷 주입 블록(핀 고정). 서버가 조회한 값이라 인용 가능하되, 숫자 날조·
# 매수/매도 판정을 금지하고 스냅샷 시각(staleness)·면책을 환기한다. report_context 와 별개.
_VIEW_CONTEXT_HEADER = (
    "\n\n[사용자가 현재 보고 있는 화면 스냅샷 — 서버가 조회한 값]\n"
    "아래는 사용자가 지금 화면에서 보고 있는 데이터의 요약 스냅샷이다(조회 시각 포함). 후속 질문에 "
    "이 값을 근거로 답하되: (1) **여기 적힌 숫자만 인용하고 새 숫자를 지어내지 마라** — 이 스냅샷에 "
    "없는 종목·수치는 '화면에 표시되지 않음'으로 다뤄라. (2) 스냅샷은 조회 시각 기준이며 실시간과 "
    "다를 수 있음을 필요 시 환기하라. (3) 매수/매도 단정 판정은 하지 말고(판정은 코드·게이트), "
    "국면·분산·게이트 관점의 참고 설명만 하며 면책을 유지하라.\n"
)


def _build_system_prompt(judgement: dict, session: Session) -> str:
    """필수 블록(build_prompt) + 세션 핀 컨텍스트(리포트·현재화면, 있으면). 단일 출처(양 경로 공유).

    두 핀 블록은 독립·선택적이며 base → report → view 순으로 덧붙인다.
    """
    prompt = build_prompt(judgement)
    if getattr(session, "report_context", None):
        prompt += _REPORT_CONTEXT_HEADER + session.report_context
    if getattr(session, "view_context", None):
        prompt += _VIEW_CONTEXT_HEADER + session.view_context
    return prompt


def _make_client():
    """기본 OpenAI 클라이언트(키는 환경변수에서만). 테스트는 client 를 주입한다."""
    from openai import OpenAI

    from infra.config import openai_api_key

    return OpenAI(api_key=openai_api_key())


def _create_with_retry(client, **kwargs):
    """create 1회 재시도. 모델별 필수 파라미터(CHAT_MODEL_PARAMS)를 병합한다.

    두 번 다 실패하면 예외를 올려 호출부가 폴백 처리. 스트리밍(stream=True)도 그대로.
    """
    merged = {**CHAT_MODEL_PARAMS, **kwargs}
    try:
        return client.chat.completions.create(**merged)
    except Exception:
        return client.chat.completions.create(**merged)


def chat(user_query: str, judgement: dict, session: Session, *, client=None) -> dict:
    """사용자 질의 → {"text","popups"}. risk_guardrail 은 LLM 미호출 차단."""
    # 1. 인텐트 사전분류 — risk_guardrail 은 코드가 결정적으로 차단(LLM 미호출).
    if classify(user_query) == "risk_guardrail":
        session.append(user_query, _GUARDRAIL_MESSAGE)
        return {"text": _GUARDRAIL_MESSAGE, "popups": []}

    if client is None:
        client = _make_client()

    messages = [{"role": "system", "content": _build_system_prompt(judgement, session)}]
    messages += session.history()
    messages.append({"role": "user", "content": user_query})

    popups: list[dict] = []
    try:
        resp = _create_with_retry(
            client,
            model=CHAT_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        choice = resp.choices[0]

        if choice.finish_reason == "tool_calls":
            messages.append(choice.message)  # assistant(tool_calls) 그대로 누적
            for tc in choice.message.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except (json.JSONDecodeError, TypeError):
                    args = {}
                if name in CONTENT_TOOLS:
                    # 콘텐츠 툴: 서버가 실행해 실제 텍스트를 되먹인다(LLM 이 요약). 팝업 아님.
                    content = run_content_tool(name, args)
                else:
                    # 표시 툴: "무엇을 띄울지"만 팝업으로 리프팅 + 확인 신호(실데이터는 프론트 조회).
                    popups.append({"name": name, "args": args})
                    content = json.dumps({"ok": True})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": name,
                        "content": content,
                    }
                )
            resp = _create_with_retry(client, model=CHAT_MODEL, messages=messages)

        text = resp.choices[0].message.content or ""
    except Exception:
        # OpenAI 전체 실패 — 크래시 대신 폴백. 세션엔 폴백 텍스트를 남긴다.
        text = _FALLBACK_MESSAGE
        popups = []

    session.append(user_query, text)
    return {"text": text, "popups": popups}


def _accumulate_tool_calls(deltas_per_chunk) -> list[dict]:
    """스트리밍 tool_calls 델타 조각을 index 별로 이어붙여 완전한 팝업 지시로 재조립한다.

    OpenAI 스트리밍 표준: 하나의 tool_call 이 여러 델타로 쪼개져 도착한다. 각 델타는
    `index`(어느 tool_call 인지)와 `function.name`/`function.arguments` 조각을 실어 온다.
    index 별로 name·arguments 문자열을 이어붙인 뒤 `json.loads` 로 args 를 복원한다.
    깨진 JSON 은 빈 dict 로 방어(팝업 지시일 뿐, 실데이터는 프론트가 조회).

    입력: 청크별 tool_calls 델타 리스트의 리스트. 반환: [{"name","args"}] (index 오름차순).
    """
    acc: dict[int, dict] = {}
    order: list[int] = []
    for deltas in deltas_per_chunk:
        for d in deltas or []:
            idx = d.index
            if idx not in acc:
                acc[idx] = {"name": "", "args": ""}
                order.append(idx)
            fn = getattr(d, "function", None)
            if fn is not None:
                if getattr(fn, "name", None):
                    acc[idx]["name"] += fn.name
                if getattr(fn, "arguments", None):
                    acc[idx]["args"] += fn.arguments

    popups: list[dict] = []
    for idx in order:
        raw = acc[idx]["args"]
        try:
            args = json.loads(raw) if raw else {}
        except (json.JSONDecodeError, TypeError):
            args = {}
        popups.append({"name": acc[idx]["name"], "args": args})
    return popups


def chat_stream(user_query: str, judgement: dict, session: Session, *, client=None):
    """사용자 질의 → 이벤트 dict 를 yield 하는 동기 제너레이터(스트리밍 경로).

    기존 chat() 과 나란히 존재하는 SSE용 경로. 같은 안전 원칙을 지킨다:
    - risk_guardrail 은 코드가 결정적으로 차단(LLM 미호출) — classify 최우선.
    - 팝업은 tool_calls 에서만 생성, 실데이터는 프론트가 조회(환각 차단).
    - 최종 누적 text 로 session.append. 예외는 폴백 token 으로 크래시 없이 마무리.

    이벤트 shape(frontend·QA 계약):
      {"type":"stage","stage": analyze|regime|generate|summarize}
      {"type":"token","text": <델타>}
      {"type":"popups","popups":[{"name","args"}]}
      {"type":"done","popups":[...]}
    (stage:analyze/regime 는 라우트가 주입하지만, guardrail 판정을 여기서 하므로
     analyze 는 chat_stream 도 선두에 낸다 — 라우트가 중복 없이 흐름을 조립한다.)
    """
    yield {"type": "stage", "stage": "analyze"}

    # 1. 인텐트 사전분류 — risk_guardrail 은 코드가 결정적으로 차단(LLM 미호출).
    if classify(user_query) == "risk_guardrail":
        session.append(user_query, _GUARDRAIL_MESSAGE)
        yield {"type": "token", "text": _GUARDRAIL_MESSAGE}
        yield {"type": "done", "popups": []}
        return

    if client is None:
        client = _make_client()

    messages = [{"role": "system", "content": _build_system_prompt(judgement, session)}]
    messages += session.history()
    messages.append({"role": "user", "content": user_query})

    popups: list[dict] = []
    full_text = ""
    try:
        yield {"type": "stage", "stage": "generate"}
        stream = _create_with_retry(
            client,
            model=CHAT_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            stream=True,
        )

        tool_deltas: list = []
        saw_tool_calls = False
        for chunk in stream:
            choice = chunk.choices[0]
            delta = choice.delta
            if getattr(delta, "tool_calls", None):
                saw_tool_calls = True
                tool_deltas.append(delta.tool_calls)
            content = getattr(delta, "content", None)
            if content:
                full_text += content
                yield {"type": "token", "text": content}

        if saw_tool_calls:
            all_calls = _accumulate_tool_calls(tool_deltas)
            # 콘텐츠 툴(summarize_youtube 등)은 팝업이 아니라 요약 소스 → 표시 popups 에서 제외.
            #   done 이벤트도 이 표시 팝업을 싣도록 외부 popups 에 배정한다.
            popups = [c for c in all_calls if c["name"] not in CONTENT_TOOLS]
            yield {"type": "popups", "popups": popups}
            # assistant(tool_calls)는 전부 되먹여야 tool 메시지와 짝이 맞는다(call_{i} 일치).
            messages.append(_assistant_tool_calls_message(all_calls))
            for i, c in enumerate(all_calls):
                if c["name"] in CONTENT_TOOLS:
                    content = run_content_tool(c["name"], c["args"])  # 실제 텍스트 되먹임
                else:
                    content = json.dumps({"ok": True})  # 표시 툴 확인 신호
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": f"call_{i}",
                        "name": c["name"],
                        "content": content,
                    }
                )
            yield {"type": "stage", "stage": "summarize"}
            stream2 = _create_with_retry(
                client, model=CHAT_MODEL, messages=messages, stream=True
            )
            for chunk in stream2:
                content = getattr(chunk.choices[0].delta, "content", None)
                if content:
                    full_text += content
                    yield {"type": "token", "text": content}
    except Exception:
        # OpenAI 전체 실패 — 크래시 대신 폴백. 세션엔 폴백 텍스트를 남긴다.
        session.append(user_query, _FALLBACK_MESSAGE)
        yield {"type": "token", "text": _FALLBACK_MESSAGE}
        yield {"type": "done", "popups": []}
        return

    session.append(user_query, full_text)
    yield {"type": "done", "popups": popups}


def _assistant_tool_calls_message(popups: list[dict]) -> dict:
    """popups 를 되먹임용 assistant(tool_calls) 메시지로 변환(호출#2 컨텍스트 유지)."""
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": f"call_{i}",
                "type": "function",
                "function": {"name": p["name"], "arguments": json.dumps(p["args"])},
            }
            for i, p in enumerate(popups)
        ],
    }
