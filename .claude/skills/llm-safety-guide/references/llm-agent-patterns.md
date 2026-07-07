# LLM 에이전트 구현 골격 (WEEK 09 챗봇)

> W06 강의 노트북(`W06_1_LLM_AI_AGENT...ipynb`, 삭제됨)에서 재사용 가치 있는 골격만 추출한 참조.
> 스킬 본문(`../SKILL.md`)의 §1 프롬프트·§2 팝업·§4 스키마·§5 안전과 함께 본다. 여기는 **구현 골격**(그 문서엔 없는 agent 루프·세션·tool JSON 형식). 강의용 예제(날씨/뉴스/YouTube/Colab/OCR)는 버렸다.
> **안전 우선(스킬 §5와 동일)**: judgement·모든 숫자는 코드가 확정 → LLM 재판정·숫자생성 금지. API 키는 환경변수만(노트북의 하드코딩 키 패턴 절대 금지). 주문 API 없음.

## 1. Agent 루프 (관찰 → 도구 → 응답) → `chat/chat.py`

챗봇의 핵심. LLM이 도구를 부르면 실행해 결과를 되먹이고 최종 답변을 만든다.

```python
def chat(user_query, judgement, session):           # judgement=매 호출 최신 국면(스킬 §1)
    messages = [{"role": "system", "content": build_prompt(judgement)}]
    messages += session.history() + [{"role": "user", "content": user_query}]

    resp = client.chat.completions.create(
        model="gpt-4o", messages=messages,
        tools=TOOLS, tool_choice="auto",            # chat/tools.py 의 스키마
    )
    choice = resp.choices[0]

    popups = []
    if choice.finish_reason == "tool_calls":
        messages.append(choice.message)             # assistant(tool_calls) 그대로 누적
        for tc in choice.message.tool_calls:
            args = json.loads(tc.function.arguments)
            popups.append({"name": tc.function.name, "args": args})   # ← 팝업 지시(데이터 아님)
            # 우리 팝업 도구는 "무엇을 띄울지"만 → tool 결과는 확인 응답(실데이터는 프론트가 조회)
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "name": tc.function.name, "content": json.dumps({"ok": True})})
        resp = client.chat.completions.create(model="gpt-4o", messages=messages)  # 최종 답변

    text = resp.choices[0].message.content or ""
    session.append(user_query, text)
    return {"text": text, "popups": popups}          # ← 스킬 §2 계약(text/popups 분리)
```

- **text/popups 분리 = tool_calls 추출**이 곧 프론트 계약(스킬 §2). 바꾸면 frontend-engineer에 알림.
- 팝업 도구의 tool 결과는 실데이터가 아니라 확인 신호 — 시세/재무는 프론트가 번들 API로 직접 조회(환각 차단).
- 여러 tool_call 병렬 가능(루프). 각 `role:"tool"` 메시지는 `tool_call_id`로 매칭.

## 2. Function calling tool JSON 스키마 → `chat/tools.py` (신규)

스킬 §2 표(팝업 3종)를 실제 OpenAI 스키마로. `description`에 **언제 호출/미호출**(오발동 방지).

```python
TOOLS = [{
    "type": "function",
    "function": {
        "name": "show_stock_report",
        "description": ("특정 종목의 분석을 요청할 때 호출한다(예 '삼성전자 어때'). "
                        "용어 설명(general_qa)이나 시장 전반 질문에는 호출하지 않는다."),
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "6자리 종목코드"},
                "stock_name": {"type": "string"},
                "focus": {"type": "string", "enum": ["fundamental", "technical", "both"]},
            },
            "required": ["ticker"],
        },
    },
}]  # show_macro_dashboard(highlight: regime|cash_ratio|indicators), show_watchlist(sort_by: ...) 동형
```

## 3. 세션 히스토리 (슬라이딩 윈도우) → `chat/session.py` (신규)

토큰 절약 + 문맥 유지. 시스템 프롬프트는 매 호출 최신 judgement로 재주입(누적 X).

```python
class Session:
    def __init__(self, window=8): self._msgs, self.window = [], window
    def history(self):                       # 시스템은 chat()이 매번 새로 주입 → 여기선 user/assistant만
        return self._msgs[-self.window:]
    def append(self, user, assistant):
        self._msgs += [{"role": "user", "content": user},
                       {"role": "assistant", "content": assistant}]
    def reset(self): self._msgs = []         # 새 대화(노트북 continuous=False)
```

- tool 메시지는 히스토리에 누적하지 않는다(다음 턴 토큰 낭비). 최종 text만 저장.
- 국면 변경 시 시스템 프롬프트가 자동 최신(재주입) — 세션 시작 1회 주입 금지(스킬 §1).

## 4. [WEEK 10 확장 부록] RAG · 외부 API 에러처리

현 W09 스펙엔 불필요(매크로·종목은 규칙/API). 사용자 업로드 자료·리포트 히스토리 유사검색 확장 시.

- **RAG 파이프라인**: 청킹(공백/문장 경계) → 임베딩(`text-embedding-3-small`, 1536차원, **배치**로 비용↓) → FAISS `IndexFlatL2`(코사인은 `IndexFlatIP`) → `index.search(q_emb, top_k)` → 반환 청크를 프롬프트 컨텍스트에 주입.
- **외부 API 호출**(KIS/DART/FRED 동일 원칙): `try/except` + status 확인 + `timeout` + **구조화 dict 반환**(에러도 `{"error": ...}`) + 부분 실패는 버리지 말고 `partial_failure`(§5.1 번들 패턴)로 표면화.

## 매핑 (WEEK 09 구현 시 참고)

| 구현 | 골격 |
|---|---|
| `chat/chat.py` | §1 agent 루프 + text/popups 분리 |
| `chat/tools.py` | §2 tool JSON 스키마(팝업 3종) |
| `chat/session.py` | §3 슬라이딩 윈도우 |
| `chat/build_prompt.py` | 스킬 §1(기준표 자동생성·필수 블록) |
| `chat` 리포트 경로 | 스킬 §4 StockReport Pydantic |
