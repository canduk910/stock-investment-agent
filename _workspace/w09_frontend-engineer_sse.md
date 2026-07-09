# W09 Frontend Engineer — 챗봇 SSE 실시간 스트리밍 UI

챗봇 응답 대기 UX를 정적 "답변 준비 중…"에서 **SSE 실시간 스트리밍**(진행 단계 체크리스트 + 토큰 라이브 타이핑)으로 전환. 기존 논스트림 `postChat`는 폴백용으로 보존. 전 구현 TDD(Red→Green).

## 테스트 목록 → 구현 (TDD 순서)

### #14 `frontend/src/lib/sseChat.js` (신규) — 파싱·리딩 분리
테스트: `src/lib/sseChat.test.js` (14개, Red 확인 후 구현)

`parseSSEBuffer(buffer)` 순수함수 (계약: `data: {json}\n\n` 프레임):
- 완성된 단일 이벤트 → 파싱 배열 + 빈 잔여
- 한 청크에 여러 이벤트 붙어 옴 → 순서대로 모두 파싱
- 이벤트 경계 가로질러 미완성으로 끝남 → 완성분만 + 잔여 버퍼 보존
- 완성 이벤트 없음(잔여만) → 빈 배열 + 원본 버퍼 유지
- popups/done 의 배열·객체 필드까지 파싱
- 빈 keep-alive(`:`)·비 data 라인 무시
- 깨진 JSON 프레임 조용히 건너뜀(크래시 금지)

`readChatStream(response, handlers)` (getReader 루프 + TextDecoder):
- stage/token/popups/done → onStage/onToken/onPopups/onDone 순서대로 디스패치
- 이벤트가 청크 경계 가로질러 쪼개져 와도 재조립
- **한글 UTF-8 바이트가 청크 경계에서 쪼개져도 손상 없이 디코드**(stream:true)
- `response.ok=false`/body 없음 → onError(무한 대기 금지)
- 핸들러 누락(선택적)이어도 크래시 없음
- **done 없이 스트림 종료 → onError**(끊긴 스트림 → 무한 스피너 금지)
- done 정상 수신 → onError 미호출

### #15-a `frontend/src/lib/chatStages.js` (신규) — 진행 단계 상태 계산
테스트: `src/lib/chatStages.test.js` (6개)
- `stageChecklist(current)`: current 이전=done(✓)·현재=active(●)·이후=pending(○). analyze/generate/summarize 각 위치 검증
- 라벨은 STAGES(한국어) 노출
- 미지/결측 stage → 첫 단계 진행으로 방어(빈 리스트·크래시 금지)
- `STAGES` = analyze→regime→generate→summarize 순서 계약 상수

### #15-b `api.js` · `ChatPanel.jsx` · `ChatMessage.jsx` · `styles.css`
- `postChatStream(sessionId, message, handlers)`: `POST /api/chat/stream` → `readChatStream`. fetch 자체 실패 시 onError(폴백 유도). 기존 `postChat` 유지.
- `ChatPanel` 스트리밍 상태기계 + `ChatMessage` 렌더 계약은 기존 프론트 테스트(popupRouter 등 60개) green 유지로 회귀 확인.

## SSE 이벤트 → 핸들러 매핑 (백엔드 계약과 대조 완료)

llm-engineer `_workspace/w09_llm-engineer_sse.md` 및 실제 백엔드 응답과 대조 — **완전 일치**.

| 이벤트 | shape | 핸들러 | ChatPanel 동작 |
|---|---|---|---|
| stage | `{type:stage, stage:analyze\|regime\|generate\|summarize}` | onStage | 봇 placeholder.stage 갱신 → 체크리스트 |
| token | `{type:token, text}` | onToken | placeholder.text += text (라이브 타이핑·자동스크롤) |
| popups | `{type:popups, popups:[{name,args}]}` | onPopups | placeholder.popups = popups |
| done | `{type:done, popups:[…]}` | onDone | streaming:false + routePopups + setPopupQueue 모달 오픈 |
| (스트림 오류) | — | onError | 논스트림 postChat 폴백 1회 → 실패 시 에러 배너 + 재시도 |

이벤트 순서(백엔드): 툴답변 `analyze→regime→generate→(token)→popups→summarize→(token)→done` · 툴없음 `analyze→regime→generate→(token)→done` · guardrail `analyze→(token 차단문)→done(popups=[])`.

## 상태기계 (ChatPanel)

`send()` → 사용자 버블 push → **봇 placeholder** `{role:bot, text:'', streaming:true, stage:analyze, popups:[]}` push → `postChatStream`.
- `patchLastBot(patch)` 헬퍼: 마지막 진행 중 봇 메시지만 부분 갱신. patch 가 함수면 이전 봇을 받아 갱신 객체 반환(token 누적 `text += t`).
- `onDone(popups)` → `finishStream`: streaming:false, text 비면 폴백 문구, routePopups→setPopupQueue(현행 모달 오픈 그대로).
- `onError` → `runChatFallback`(1회, `fellBack` 가드): postChat 결과로 placeholder 교체. 폴백도 실패 시 placeholder 제거 + 에러 배너 + 재시도(`lastQueryRef`).
- 입력·전송 버튼은 `loading`(스트리밍 중 true)으로 비활성. 무한 스피너 없음.

## ChatMessage 렌더 (streaming/stage props 추가)

- `showStages = streaming && !text`: 토큰 도착 전엔 `ChatStages`(체크리스트), 토큰 오면 사라지고 라이브 타이핑 텍스트 + `.chat__cursor` 깜빡임.
- 완료(streaming:false) 시 커서·체크리스트 사라지고 최종 텍스트 + 팝업 재열기 칩만 남음.

## 스타일 (styles.css — theme.css 토큰만, hex/초록/황색 0)

- `.chat__stages` 체크리스트: 완료=✓ 파랑(`--c-blue-strong`)·현재=● 파랑(`--c-blue`) `@keyframes stage-pulse`·대기=○ 회색(`--c-text-muted`)
- `.chat__cursor` 타이핑 커서: `--c-blue` 세로 막대 + `@keyframes blink`
- 하드코딩 hex/금지색 검사 통과(grep 0건)

## 검증

- `npm test` — **60 passed**(기존 40 + 신규 sseChat 14 + chatStages 6)
- `npm run build` — 성공(52 modules)
- **실 백엔드 통합**: `POST /api/chat/stream` guardrail 입력(키 불요) → 실제 프레임 `analyze→token(차단문)→done(popups=[])` + 헤더 `text/event-stream`·`no-cache`·`X-Accel-Buffering:no` 확인. 실제 응답 바이트를 임의 7바이트 경계로 쪼개 `parseSSEBuffer` 재조립 → `stage,token,done` 정합 PASS.
- 안전 불변: 팝업 실데이터는 프론트 직접 조회(불변, popups→routePopups→컴포넌트가 fetch), 면책 고지 상시(DISCLAIMER), guardrail LLM 미호출 결정적(백엔드), routePopup 계약 불변.

## 파일
- 신규: `frontend/src/lib/sseChat.js`·`sseChat.test.js`, `frontend/src/lib/chatStages.js`·`chatStages.test.js`
- 수정: `frontend/src/api.js`(postChatStream), `frontend/src/components/ChatPanel.jsx`(상태기계), `frontend/src/components/ChatMessage.jsx`(streaming/stage 렌더), `frontend/src/styles.css`(체크리스트·커서)
