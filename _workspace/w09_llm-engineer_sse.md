# W09 LLM Engineer — SSE 백엔드 스트리밍

기존 동기 `chat()` + `POST /api/chat`는 그대로 유지(폴백·회귀). 스트리밍 경로를 나란히 추가.
전체 회귀: **281 passed**(기존 270 + 신규 11), 9 deselected(live).

## 테스트 목록 → 구현 (TDD Red→Green)

### #12 `chat/chat.py` — `chat_stream()` + `_accumulate_tool_calls()`
테스트: `tests/unit/chat/test_chat_stream.py` (8개, FakeStreamClient가 델타 청크 yield)
- `test_accumulate_tool_calls_reassembles_name_and_args_fragments` — 하나의 tool_call이 여러 델타로 쪼개져(id·name 한 조각, args 여러 조각) 도착 → index별 이어붙여 `{ticker:"005930"}` 복원
- `test_accumulate_tool_calls_handles_multiple_indices` — 여러 tool_call(index 0,1) 동시 재조립, 순서 보존
- `test_accumulate_tool_calls_bad_json_yields_empty_args` — 깨진 JSON → args={} 방어(팝업 지시일 뿐, 실데이터는 프론트)
- `test_guardrail_blocks_without_calling_llm` — classify==risk_guardrail → `client.calls==[]`(LLM 미호출), analyze stage + 차단 token + done(popups=[]) + session.append
- `test_no_tool_calls_streams_tokens_and_appends_session` — content 델타 → token 누적 = 전체 text, stream=True·tools 주입·model=gpt-5.4, 누적 text로 session.append
- `test_tool_calls_stream_emits_popups_then_narration` — tool_calls 델타 재조립 → popups 이벤트 → 호출#2 stream=True narration 토큰 → done(popups=[...]), calls==2
- `test_generate_stage_emitted_before_tokens` — generate stage가 첫 token보다 앞
- `test_exception_falls_back_to_fallback_message` — 예외 → `_FALLBACK_MESSAGE` token + done, session.append

### #13 `api/chat.py` — `POST /api/chat/stream`
테스트: `tests/unit/api/test_chat_stream_route.py` (3개, chat_stream·live_judgement mock)
- `test_stream_normal_flow_orders_stages_and_forwards_judgement` — media_type text/event-stream, Cache-Control:no-cache·X-Accel-Buffering:no 헤더, stage 순서 `[analyze, regime, generate]`, live_judgement 실행·judgement가 chat_stream에 전달
- `test_stream_guardrail_skips_regime_stage` — guardrail이면 regime 미주입 + **live_judgement 미실행**(FRED 낭비 없음)
- `test_stream_reuses_session_across_calls` — 같은 session_id → 같은 Session 인스턴스

## SSE 이벤트 계약 (frontend·QA 단일 출처 — 변경 금지)

`api/chat.py::_sse`가 각 이벤트를 `f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"`로 프레이밍.

**stage enum** = `analyze | regime | generate | summarize`
- `analyze` — 질문 분석(classify)
- `regime` — 시장 국면 조회(live_judgement/FRED). **guardrail 경로에선 미발생**
- `generate` — 답변 작성 중(gpt-5.4 호출#1)
- `summarize` — 정리 중(tool_calls 후 narration 호출#2). 툴 없는 답변에선 미발생

**이벤트 shape 4종** (`type`으로 분기):
```
{"type":"stage",  "stage": "<enum>"}
{"type":"token",  "text": "<델타 문자열>"}
{"type":"popups", "popups": [{"name": "<툴명>", "args": {...}}]}
{"type":"done",   "popups": [{"name","args"}, ...]}   # 항상 마지막, 최종 popups 확정
```

**이벤트 순서(정상 툴 답변)**: `analyze → regime → generate → (token…) → popups → summarize → (token…) → done`
**툴 없는 답변**: `analyze → regime → generate → (token…) → done`
**guardrail**: `analyze → (token: 차단문) → done(popups=[])` — regime/generate 없음, LLM 미호출

`popups[].name` ∈ {show_macro_dashboard, show_stock_report, show_watchlist}, args는 `chat/tools.py` TOOLS enum. 프론트는 `onDone(popups)`에서 기존 `routePopups`로 모달 오픈(현행 그대로).

## tool_calls 재조립 방식 (`_accumulate_tool_calls`)

OpenAI 스트리밍은 하나의 tool_call을 여러 델타로 쪼개 보낸다. 각 델타는 `index`(어느 tool_call) + `function.name`/`function.arguments` **조각**을 실어옴.
1. index별 dict 누적: `name`·`args` 문자열을 조각 이어붙임(name은 보통 첫 델타에만, args는 여러 델타에 분산)
2. 완성 후 `json.loads(args_str)` → 실패 시 `{}` 방어
3. index 등장 순서로 `[{name, args}]` 반환

narration 호출#2 컨텍스트: 재조립된 popups를 `_assistant_tool_calls_message()`로 assistant(tool_calls) 메시지 + tool(`{"ok":True}`) 응답으로 되먹임(실데이터 아님, 확인 신호만).

## 안전 불변 유지
- guardrail: 라우트(classify)와 chat_stream(classify) **이중 판정**, LLM 미호출을 테스트로 실증(client.calls==[])
- 팝업은 tool_calls에서만, 실데이터 미생성(프론트 조회)
- CHAT_MODEL="gpt-5.4" 단일 출처(tools.py), 면책 고지는 build_prompt 유지
- 예외는 폴백 token으로 크래시 없이 마무리
- 기존 chat()·/api/chat 무변경

## 파일
- `chat/chat.py` — `chat_stream()`, `_accumulate_tool_calls()`, `_assistant_tool_calls_message()` 추가
- `api/chat.py` — `POST /api/chat/stream`, `_sse()` 추가
- `tests/unit/chat/test_chat_stream.py`, `tests/unit/api/test_chat_stream_route.py` 신규
