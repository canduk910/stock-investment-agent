"""팝업/관리 도구 function calling 스키마 + 모델 상수 — llm-safety-guide §2.

이 파일의 두 가지가 계약이다:
1. CHAT_MODEL — 챗봇·데이터 생성 LLM 모델 ID 단일 출처(사용자 결정: gpt-5.6-luna).
   코드 어디에도 모델 문자열을 다시 타이핑하지 않는다(문자열 산재 = 불일치의 씨앗).
2. TOOLS — 팝업 3종 스키마. name·enum·required 는 frontend 팝업 라우팅과의 계약
   (QA 경계면 #2·#3). LLM 은 "무엇을 띄울지"만 결정하고, 실데이터는 프론트가 API 로
   직접 조회한다(환각 차단, 스킬 §2). 그래서 tool 은 표시 지시일 뿐 데이터를 만들지 않는다.

각 description 에 "언제 호출하는지"와 "언제 호출하지 않는지"를 모두 명시한다(오발동 방지).
파라미터는 enum 으로 제한해 프론트가 분기할 값의 집합을 닫는다.
"""
from __future__ import annotations

# 챗봇·데이터 생성 LLM 모델 ID 단일 출처(사용자 결정 오버라이드: gpt-4o 아님).
CHAT_MODEL = "gpt-5.6-luna"

# 모델별 필수 create() 파라미터(단일 출처) — 매 chat.completions.create 호출에 병합한다.
#   gpt-5.6-luna 는 추론형이라, chat/completions 에서 function tools 를 쓰려면
#   reasoning_effort='none' 이 필요하다(미지정 시 기본 추론 모드가 tools 와 비호환 → 400
#   "Function tools with reasoning_effort are not supported ..."). 또 이 계열은 구형
#   `max_tokens`/`temperature` 를 받지 않으므로 앱은 그 둘을 넘기지 않는다.
#   모델을 비추론형(예: gpt-4o)으로 바꾸면 이 dict 를 비우면 된다({}).
CHAT_MODEL_PARAMS = {"reasoning_effort": "none"}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "show_macro_dashboard",
            "description": (
                "시장 전반·현재 국면·권장 현금비중·매크로 지표를 물을 때 호출한다"
                "(예 '지금 시장 어때', '현금 얼마나 들고 있어야 해'). "
                "특정 종목 분석 요청이나 단순 용어 설명에는 호출하지 않는다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "highlight": {
                        "type": "string",
                        "description": "강조할 영역(국면/현금비중/지표)",
                        "enum": ["regime", "cash_ratio", "indicators"],
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_stock_report",
            "description": (
                "특정 종목의 분석·리포트를 요청할 때 호출한다(예 '삼성전자 어때', "
                "'005930 밸류에이션 봐줘'). 시장 전반 질문(show_macro_dashboard)이나 "
                "용어 설명(general_qa)에는 호출하지 않는다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "6자리 종목코드"},
                    "stock_name": {"type": "string", "description": "종목명(있으면)"},
                    "focus": {
                        "type": "string",
                        "description": "분석 초점(기본적/기술적/둘 다)",
                        "enum": ["fundamental", "technical", "both"],
                    },
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_watchlist",
            "description": (
                "관심종목(워치리스트) 목록을 보고 싶을 때 호출한다(예 '내 관심종목 보여줘', "
                "'목표가 근접한 종목 있어'). 특정 종목 상세 분석이나 시장 전반 질문에는 "
                "호출하지 않는다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sort_by": {
                        "type": "string",
                        "description": "정렬 기준(등록순/등락률/목표가근접)",
                        "enum": ["registered", "change_rate", "near_target"],
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manage_watchlist",
            "description": (
                "관심종목을 추가/제거하거나 목표가를 설정해 달라고 할 때 호출한다"
                "(예 '삼성전자 관심종목에 담아줘', '005930 목표가 8만원', '카카오 관심목록에서 빼줘'). "
                "단순 목록 조회(show_watchlist)나 종목 분석(show_stock_report)에는 호출하지 않는다. "
                "이 도구는 '무엇을 할지 제안'만 하며, 실제 변경은 사용자가 화면에서 확인(confirm)해야 "
                "반영된다 — 네가 직접 매매하거나 자동 실행하지 않는다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "수행할 작업(추가/제거/목표가 설정)",
                        "enum": ["add", "remove", "set_target"],
                    },
                    "ticker": {"type": "string", "description": "6자리 종목코드"},
                    "stock_name": {"type": "string", "description": "종목명(있으면)"},
                    "target_price": {"type": "number", "description": "set_target 시 목표가(원)"},
                },
                "required": ["action", "ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_balance",
            "description": (
                "사용자가 계좌 잔고·보유종목·평가액·수익/손실 현황을 물을 때 호출한다"
                "(예 '내 잔고 봐줘', '내 계좌 상태 어때', '수익 얼마야', '지금 얼마 벌었어'). "
                "리밸런싱·분산 조언이나 단순 용어 설명·시장 전반 질문에는 호출하지 않는다"
                "(조언은 팝업 없이 텍스트로만 설명한다). "
                "이 도구는 '무엇을 띄울지'만 지시하며, 실제 잔고 숫자는 화면이 직접 조회한다"
                "(네가 평가액·수익을 지어내지 않는다)."
            ),
            # 파라미터 없음: 단일 사용자 계좌 — 프론트가 /api/balance 를 자체조회한다.
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_youtube",
            "description": (
                "사용자가 특정 YouTube 영상 내용을 요약·정리해 달라거나 '이 영상 뭐래?'처럼 "
                "URL과 함께 물을 때 호출한다(예 '이 영상 요약해줘 https://youtu.be/…'). "
                "URL 없이 일반 시황·종목을 물을 때는 호출하지 않는다. "
                "영상 자막은 화자의 의견이므로 '영상에 따르면'으로 출처를 밝혀 요약하고, "
                "매수/매도 판정으로 제시하지 않는다(설명만)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "video_url": {"type": "string", "description": "YouTube 영상 URL"},
                },
                "required": ["video_url"],
            },
        },
    },
]


# ── 콘텐츠 툴(표시 팝업이 아니라, LLM 이 결과 텍스트를 소비·요약) ────────────────
# 표시 툴(show_*)은 chat.py 가 tool 결과를 {"ok":True}로만 되먹이고 실데이터는 프론트가
# 조회(환각 차단). 콘텐츠 툴은 서버가 실행해 실제 텍스트를 되먹여 LLM 이 요약한다.
# 이름 집합 + 실행 레지스트리가 단일 출처 — chat.py(chat·chat_stream)가 이걸로 분기한다.
CONTENT_TOOLS = frozenset({"summarize_youtube"})


def _impl_summarize_youtube(args: dict) -> str:
    # 지연 import — tools.py 로드가 youtube_transcript_api 유무에 묶이지 않게.
    from collectors.youtube import fetch_transcript

    url = (args or {}).get("video_url", "")
    transcript = fetch_transcript(url)
    if not transcript:
        return (
            "자막을 가져오지 못했습니다(비공개·자막 없음·불량 URL 가능). "
            "사용자에게 다른 영상이나 URL 확인을 안내하세요."
        )
    return (
        "[아래는 해당 YouTube 영상 화자의 발언 자막이다 — 3자 의견이므로 '영상에 따르면'으로 "
        "출처를 밝혀 요약하고, 매수/매도 판정으로 제시하지 말 것]\n" + transcript
    )


_TOOL_IMPL = {"summarize_youtube": _impl_summarize_youtube}


def run_content_tool(name: str, args: dict) -> str:
    """콘텐츠 툴 실행 → LLM 되먹임용 문자열. 미등록·예외는 안전 메시지(챗 안 죽임)."""
    impl = _TOOL_IMPL.get(name)
    if impl is None:
        return "요청을 처리할 수 없습니다."
    try:
        return impl(args or {})
    except Exception:
        return "콘텐츠를 불러오는 중 문제가 발생했습니다."
