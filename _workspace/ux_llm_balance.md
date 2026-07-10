# UX3 — show_balance 툴 + build_prompt 규칙 (llm-engineer)

Task #13. TDD Red→Green. llm-safety-guide 준수. LLM은 "무엇을 띄울지"만, 잔고 숫자는 프론트가 조회.

## 계약 (frontend-engineer-2 · qa-inspector 대상)

- **툴 이름**: `show_balance` (팝업 4종 → **5종**으로 확장)
- **파라미터**: 없음 — `"parameters": {"type": "object", "properties": {}}`. 단일 사용자 계좌라 인자 불필요, `required` 없음.
- **chat 응답 shape 불변**: `{text, popups:[{name, args}]}`. show_balance 호출 시 `popups=[{"name":"show_balance","args":{}}]`.
- **popupRouter 매핑 필요**: `show_balance → kind 'balance'` (frontend-engineer-2가 `lib/popupRouter.js`·`POPUP_KIND` 5종 갱신). 이 계약이 어긋나면 잔고 팝업이 조용히 안 뜬다.

## 테스트 목록 (스펙 근거 → 구현 순서, test-first)

### tests/unit/chat/test_tools.py (갱신)
1. `test_popup_tool_names__frontend_contract` — 이름 집합 5종(+show_balance). [프론트 라우팅 계약]
2. `test_show_balance_has_no_parameters` — `properties=={}`, `required` 없음. [단일 계좌·프론트 자체조회]
3. `test_show_balance_description_states_when_to_call_and_not` — "잔고" 포함 + "호출하지 않는다" 포함. [오발동 방지, 스킬 §2]
4. `test_descriptions_state_when_not_to_call__misfire_guard` — misfire 가드 루프에 show_balance 추가(5종 전수). [기존 가드 확장]

### tests/unit/chat/test_build_prompt.py (추가)
5. `test_prompt_has_show_balance_rule_in_popup_block` — ⑦에 `show_balance` + "잔고" 존재.
6. `test_prompt_says_rebalance_advice_is_text_only` — "리밸런싱" 조언은 텍스트만(팝업 없음).

**Red 확인**: 6 failed(전부 assertion 실패, import 에러 아님) → Green 후 24 passed.

## 구현 (Green — 최소)

- `chat/tools.py`: `TOOLS` 끝에 `show_balance` 추가. description에 언제 호출(잔고·평가액·수익/손실 현황 질문)/미호출(리밸런싱·분산 조언·단순질문·시장 전반) 모두 명시 + "실제 잔고 숫자는 화면이 직접 조회(네가 지어내지 않는다)". `CHAT_MODEL` 불변(gpt-5.4).
- `chat/build_prompt.py` ⑦ 팝업 규칙에 2줄 추가:
  - "계좌 잔고·보유종목·평가액·수익/손실 → show_balance 호출(파라미터 없음), 실제 숫자는 화면 조회"
  - "리밸런싱·분산 조언은 팝업 없이 텍스트로만 — 명령형('팔아라/사라') 금지, 국면 현금비중·분산 원칙 참고 설명". **숫자 하드코딩 0**.
- `chat/chat.py`: **변경 없음**(확인만). `chat()` 87–92행과 `chat_stream`의 `_accumulate_tool_calls`가 `tc.function.name`을 하드코딩 없이 그대로 popups로 포워딩 → 새 툴 자동 통과.
- 인텐트 라벨 신규 없음(tool_choice가 팝업 여부 결정, 인텐트는 guardrail만 게이트).

## 안전 (llm-safety-guide §5)

- LLM은 설명만: 잔고 데이터는 코드(프론트 /api/balance)가 정규화, LLM 미개입.
- 리밸런싱은 "조언/설명"만 — 명령형·자동주문 문구 없음(프롬프트에 명령형 금지 명시).
- 면책 고지 블록 불변(⑥ 유지).

## 검증

- `uv run pytest tests/unit/chat -q` → **104 passed**.
- 전체(내 파일 무관 KisConfig collection 에러 3개 = data-engineer-2 Task #12 진행 중 제외) → **438 passed, 0 failed**. 내 변경 회귀 없음.
- 라이브 미호출(FakeOpenAI mock 경로만).

## 변경 파일

- `chat/tools.py` (show_balance 추가)
- `chat/build_prompt.py` (⑦ 2줄)
- `tests/unit/chat/test_tools.py` (5종 계약·파라미터·가드)
- `tests/unit/chat/test_build_prompt.py` (잔고 팝업 규칙 2건)
