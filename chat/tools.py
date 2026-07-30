"""팝업/관리 도구 function calling 스키마 + 모델 상수 — llm-safety-guide §2.

이 파일의 두 가지가 계약이다:
1. 하이브리드 모델 상수(단일 출처) — 코드 어디에도 모델 문자열을 다시 타이핑하지 않는다
   (문자열 산재 = 불일치의 씨앗). 용도별 2개 상수:
     - CHAT_MODEL   = 상위 terra — **일반 대화(사용자 대면)**: chat()/chat_stream() 1차(tools)·
                       2차(tool 결과 되먹임 후 최종 답변). 대화 품질 우선.
     - REPORT_MODEL = 하위 luna — **정형 작업**: structured_summary(리포트·애널리스트·시황
                       요약 5 summarizer)·_reclassify_risk(안전 재분류)·intent_gen(오프라인
                       학습데이터 생성). 스키마/JSON 강제라 하위로 충분, 비용·지연 절감.
   어느 호출이 어느 상수인지는 chat/CLAUDE.md 표가 SSOT.
2. TOOLS — 팝업 스키마. name·enum·required 는 frontend 팝업 라우팅과의 계약(QA 경계면 #2·#3).
   LLM 은 "무엇을 띄울지"만 결정하고, 실데이터는 프론트가 API 로 직접 조회한다(환각 차단, 스킬 §2).

각 description 에 "언제 호출하는지"와 "언제 호출하지 않는지"를 모두 명시한다(오발동 방지).
파라미터는 enum 으로 제한해 프론트가 분기할 값의 집합을 닫는다.
"""
from __future__ import annotations

# ── 하이브리드 LLM 모델 ID 단일 출처(사용자 결정) ──────────────────────────────
# 일반 대화(상위) — 사용자에게 보이는 대화 응답. chat()/chat_stream() 1차·2차가 참조.
CHAT_MODEL = "gpt-5.6-terra"
# 리포트·요약·분류·오프라인 생성(하위) — 정형 작업. structured_summary·_reclassify_risk·
# intent_gen 이 참조. 스키마 강제라 하위 모델로 품질 충분하고 비용/지연을 아낀다.
REPORT_MODEL = "gpt-5.6-luna"

# 모델별 필수 create() 파라미터(단일 출처) — 매 chat.completions.create 호출에 병합한다.
#   terra·luna 는 둘 다 추론형이라, chat/completions 에서 function tools 를 쓰려면
#   reasoning_effort='none' 이 필요하다(미지정 시 기본 추론 모드가 tools 와 비호환 → 400
#   "Function tools with reasoning_effort are not supported ..."). 또 이 계열은 구형
#   `max_tokens`/`temperature` 를 받지 않으므로 앱은 그 둘을 넘기지 않는다.
#   어느 한 모델을 비추론형(예: gpt-4o)으로 바꾸면 그 모델의 PARAMS 를 {} 로 비운다.
CHAT_MODEL_PARAMS = {"reasoning_effort": "none"}    # terra(일반 대화)용
REPORT_MODEL_PARAMS = {"reasoning_effort": "none"}  # luna(정형 작업)용

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
                "관심종목을 추가/제거하거나 매수/매도 목표가를 설정해 달라고 할 때 호출한다"
                "(예 '삼성전자 관심종목에 담아줘', '005930 매수 목표가 8만원', "
                "'매도 목표가 12만원으로 잡아줘', '카카오 관심목록에서 빼줘'). "
                "네가 근거와 함께 추천한 목표가를 사용자가 반영하려 할 때도 set_target 으로 제안한다. "
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
                    "target_price": {
                        "type": "number",
                        "description": "set_target 시 매수 목표가(원) — '사고 싶은 가격'. 매도만 설정하면 생략.",
                    },
                    "sell_target_price": {
                        "type": "number",
                        "description": "set_target 시 매도 목표가(원) — '팔고 싶은 가격'. 매수만 설정하면 생략.",
                    },
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
            "name": "show_screener",
            "description": (
                "대순환 후보 종목 목록 패널을 우측에 연다. 사용자가 '후보 종목 보여줘/확인', "
                "'대순환 후보 화면 열어줘' 처럼 대순환 후보 종목 **목록·화면을 보고 싶어할 때** 호출한다. "
                "종목 추천/후보를 물으면 설명·근거는 screen_stocks(콘텐츠 툴)로 전하고, 이 도구는 그 목록 "
                "패널을 함께 띄우는 용도다(실제 후보 데이터는 화면이 직접 조회한다 — 네가 지어내지 않는다)."
            ),
            # 파라미터 없음: 후보 종목 패널(ScreenerPanel)이 시장·단계 필터를 자체 관리·조회한다.
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
    {
        "type": "function",
        "function": {
            "name": "search_report",
            "description": (
                "사용자가 인덱싱된 증권사/애널리스트 리포트의 내용을 물을 때 호출한다"
                "(예 '이 리포트 요약해줘', '리포트에서 목표주가 뭐래?', '삼성전자 리포트 핵심'). "
                "일반 시황·시세·잔고 질문에는 호출하지 않는다(그건 show_* 도구). "
                "이 도구는 팝업이 아니라 리포트 본문 발췌를 가져와 네가 요약·답변하는 용도다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "리포트에서 찾을 질문/키워드"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_analyst_reports",
            "description": (
                "특정 종목의 네이버 애널리스트 리포트를 새로 **수집·요약**해 온다. "
                "사용자가 '이 종목 리포트 확보/가져와/수집해줘'라고 하거나, 저장된 리포트가 없어 "
                "사용자가 수집에 동의했을 때만 호출한다(수십 초 걸리는 작업 — 원하지 않으면 호출하지 않는다). "
                "이미 인덱싱된 업로드 PDF 검색은 search_report 를 쓰고, 이 도구는 네이버에서 새로 가져오는 용도다. "
                "결과 요약은 '리포트에 따르면'으로 출처를 밝혀 전하고 매수/매도 판정으로 제시하지 않는다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "종목코드 6자리(예: 058610)"},
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "screen_stocks",
            "description": (
                "대순환(이동평균선 배열) 단계로 시총상위 종목을 스캔해 후보 종목을 안내한다. "
                "사용자가 **특정 종목을 지정하지 않고** '종목 추천해줘 / 좋은·괜찮은·유망 종목 알려줘 / "
                "후보 종목 알려줘·찾아줘·추천해줘 / 어떤 종목이 좋아 / 대순환 상승(N단계) 종목' 처럼 "
                "**새 종목 후보 발굴·추천**을 물으면 호출한다(막연한 일반론·방어주 나열 대신 이 도구로 실제 후보 제시). "
                "규칙 엔진(코드) 산출 **기술적 분류**이지 에이전트의 매수 추천이 아니다 — '스크리너에 따르면'으로 엔진에 귀속. "
                "구분: 사용자의 기존 '관심종목' 목록 확인은 show_watchlist, 보유 잔고는 show_balance, "
                "특정 개별 종목 하나 분석은 show_stock_report — 이 도구는 '새 종목 발굴 추천'용이다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "market": {
                        "type": "string",
                        "enum": ["all", "kospi", "kosdaq", "kospi200"],
                        "description": "시장(기본 all)",
                    },
                    "stage": {
                        "type": "string",
                        "description": "단계 필터: 'rising'(상승국면 1·6단계, 기본) / '1'~'6'(특정 단계) / 'all'(전체)",
                    },
                },
            },
        },
    },
]


# ── 콘텐츠 툴(표시 팝업이 아니라, LLM 이 결과 텍스트를 소비·요약) ────────────────
# 표시 툴(show_*)은 chat.py 가 tool 결과를 {"ok":True}로만 되먹이고 실데이터는 프론트가
# 조회(환각 차단). 콘텐츠 툴은 서버가 실행해 실제 텍스트를 되먹여 LLM 이 요약한다.
# 이름 집합 + 실행 레지스트리가 단일 출처 — chat.py(chat·chat_stream)가 이걸로 분기한다.
CONTENT_TOOLS = frozenset(
    {"summarize_youtube", "search_report", "fetch_analyst_reports", "screen_stocks"}
)

# 챗에서 애널리스트 리포트 수집 시 상한(지연 캡) — 프론트 '가져오기'(최대 30)보다 작게 잡아
# 챗 응답이 과도하게 지연되지 않게 한다(각 리포트마다 PDF 다운로드 + LLM 요약이라 느림).
ANALYST_CHAT_FETCH_LIMIT = 5
_ANALYST_FEEDBACK_TOP_N = 5  # 되먹임에 실을 최근 리포트 수

# 스크리너 콘텐츠 툴 — 스캔 규모 + 되먹임 상한(1500자 예산 내). 상승국면 기본(1·6단계).
_SCREEN_CHAT_SIZE = 30
_SCREEN_FEEDBACK_TOP_N = 20  # 되먹임 원라인 상한
_SCREEN_RISING_STAGES = (1, 6)  # 상승국면(1 안정상승 · 6 상승진입)


def _looks_like_ticker(t) -> bool:
    """6자리 숫자 종목코드 여부(불량 티커로 불필요한 네이버 크롤 방지)."""
    return isinstance(t, str) and t.isdigit() and len(t) == 6


def _impl_search_report(args: dict, *, user=None, db=None) -> str:
    # 지연 import — tools.py 로드가 rag(pdfplumber/numpy) 유무에 묶이지 않게. (user/db 미사용)
    from rag import store

    query = (args or {}).get("query", "")
    hits = store.search_reports(query, top_k=3)
    if not hits:
        return (
            "인덱싱된 증권사 리포트가 없거나 관련 내용을 찾지 못했습니다. "
            "reports 폴더에 PDF를 넣고 재인덱스(POST /api/reports/reindex)했는지 사용자에게 안내하세요."
        )
    blocks = [f"[출처: {h.get('source', '?')}]\n{h.get('text', '')}" for h in hits]
    return (
        "[아래는 증권사 리포트 발췌다 — '리포트에 따르면'으로 출처를 밝혀 요약/답변하고, "
        "에이전트 자체 매수/매도 판정으로 제시하지 말 것]\n" + "\n\n".join(blocks)
    )


def _impl_summarize_youtube(args: dict, *, user=None, db=None) -> str:
    # 지연 import — tools.py 로드가 youtube_transcript_api 유무에 묶이지 않게. (user/db 미사용)
    from collectors.youtube import fetch_transcript_detailed

    url = (args or {}).get("video_url", "")
    transcript, reason = fetch_transcript_detailed(url)
    if not transcript:
        # 분류된 사유를 그대로 전달(IP 차단 / 자막 없음 / 접근 불가 / 타임아웃 구분) — 사용자에게 정확히 안내.
        return f"자막을 가져오지 못했습니다. 사유: {reason} 이 사유를 사용자에게 그대로 안내하세요."
    return (
        "[아래는 해당 YouTube 영상 화자의 발언 자막이다 — 3자 의견이므로 '영상에 따르면'으로 "
        "출처를 밝혀 요약하고, 매수/매도 판정으로 제시하지 말 것]\n" + transcript
    )


def _impl_fetch_analyst_reports(args: dict, *, user=None, db=None) -> str:
    # 네이버에서 그 종목 애널리스트 리포트를 수집·요약·저장(느림 — 요청 시만 프롬프트가 호출) →
    # 저장된 요약을 출처 귀속 프레이밍으로 되먹여 LLM 이 인용해 답한다(에이전트 판정 아님). (user/db 미사용)
    ticker = str((args or {}).get("ticker", "")).strip()
    if not _looks_like_ticker(ticker):
        return "종목코드(6자리)를 확인하지 못해 애널리스트 리포트를 수집할 수 없습니다."

    # 지연 import — tools.py 로드가 수집 스택(requests/pdfplumber/OpenAI)에 묶이지 않게.
    from chat import analyst_service
    from chat.analyst_store import default_store

    result = analyst_service.fetch_and_summarize_for_ticker(ticker, limit=ANALYST_CHAT_FETCH_LIMIT)
    reports = default_store().list_reports(ticker)[:_ANALYST_FEEDBACK_TOP_N]
    if not reports:
        return (
            f"네이버에서 {ticker} 관련 애널리스트 리포트를 찾지 못했습니다"
            f"(발견 {result.get('fetched', 0)}건). 최근 공개된 리포트가 없을 수 있음을 알리고 "
            "없는 목표주가·의견을 지어내지 마세요."
        )
    header = (
        f"[{ticker} 애널리스트 리포트 수집 결과 — 발견 {result.get('fetched', 0)}·신규 "
        f"{result.get('new', 0)}·기존 {result.get('skipped', 0)}·실패 {result.get('failed', 0)}건. "
        "아래는 각 증권사 리포트가 밝힌 의견이다(에이전트 판정 아님). "
        "'리포트에 따르면'으로 출처를 밝혀 전하고, 매수/매도 단정·수치 날조 금지·면책 유지]"
    )
    lines = [header]
    for e in reports:
        s = e.get("summary") or {}
        broker = s.get("증권사") or e.get("broker") or "증권사"
        opinion = s.get("투자의견") or "의견 명시 없음"
        target = s.get("목표주가") or "목표가 없음"
        brief = (s.get("요약") or "")[:120]
        lines.append(f"- [{broker}] 의견 {opinion} · 목표가 {target} — {brief}")
    return "\n".join(lines)


def _screen_stage_filter(stage) -> tuple[int, ...] | None:
    """stage 인자 → 허용 단계 튜플. None(전체) / (1,6)(상승국면 기본) / (n,)(특정)."""
    s = str(stage or "rising").strip().lower()
    if s == "all":
        return None
    if s in ("1", "2", "3", "4", "5", "6"):
        return (int(s),)
    return _SCREEN_RISING_STAGES  # rising·미지정·불량 → 상승국면(1·6)


def _impl_screen_stocks(args: dict, *, user=None, db=None) -> str:
    # 대순환 스크리너(규칙 엔진·코드)로 시총상위 종목의 대순환 단계를 스캔 → 단계 필터 후 출처 귀속
    # 프레이밍으로 되먹인다. 판정은 엔진(코드)·설명은 LLM. 매수 추천 아님·면책은 프롬프트+헤더 이중 강조.
    # 지연 import — tools.py 로드가 KIS/스크리너 스택에 묶이지 않게, 사이클(api.detail) 회피.
    from api.detail import _resolve_client
    from collectors.kis.ranking import MARKET_ISCD
    from stock.screener import screen_grand_cycle

    market = str((args or {}).get("market", "all")).strip().lower()
    if market not in MARKET_ISCD:
        market = "all"
    stages = _screen_stage_filter((args or {}).get("stage"))

    # 프로덕션은 KIS 앱키가 __shared__ DB 에만 있어 db 필수(env fallback 은 비어 있음 — 잔고 P2 교훈).
    client = _resolve_client(user, db)
    result = screen_grand_cycle(client, market_iscd=MARKET_ISCD[market], size=_SCREEN_CHAT_SIZE)
    candidates = result.get("candidates") or []
    # 단계 필터(기본 상승국면). 판정보류(stage=None)는 항상 제외.
    picked = [c for c in candidates if c.get("stage") is not None and
              (stages is None or c.get("stage") in stages)]

    market_label = {"all": "전체", "kospi": "코스피", "kosdaq": "코스닥", "kospi200": "코스피200"}[market]
    stage_label = "전체 단계" if stages is None else (
        "상승국면(1·6단계)" if stages == _SCREEN_RISING_STAGES else f"{stages[0]}단계"
    )
    if not picked:
        return (
            f"[대순환 스크리너({market_label}·{stage_label})] 해당 조건의 후보 종목이 없습니다. "
            "없는 종목·목표가를 지어내지 말고, 다른 단계·시장을 제안하세요."
        )
    header = (
        f"[대순환 스크리너 결과({market_label}·{stage_label}) — 규칙 엔진(코드)이 산출한 대순환 단계 "
        "스캔이며 에이전트의 매수 추천이 아니다. '스크리너에 따르면 이 종목들이 …단계로 분류됨'처럼 판정 "
        "주체를 엔진에 귀속해 전하고, 특정 종목을 '사라'고 단정하거나 수익을 보장하지 말 것. 아래 종목명·단계·"
        "밴드 수치만 인용(날조 금지)·손실 위험 환기·면책 유지]"
    )
    lines = [header]
    for c in picked[:_SCREEN_FEEDBACK_TOP_N]:
        band = c.get("band_width_pct")
        band_s = f" · 밴드 {band:+.1f}%" if isinstance(band, (int, float)) else ""
        if c.get("band_direction"):
            band_s += f"({c['band_direction']})"
        # stage_name 은 스크리너가 constants(SSOT)에서 붙인 라벨 — LLM 복제 아님.
        lines.append(
            f"- {c.get('name') or c.get('ticker')}({c.get('ticker')}) "
            f"{c.get('stage')}단계·{c.get('stage_name') or ''}{band_s}"
        )
    if len(picked) > _SCREEN_FEEDBACK_TOP_N:
        lines.append(f"…외 {len(picked) - _SCREEN_FEEDBACK_TOP_N}종목")
    return "\n".join(lines)


_TOOL_IMPL = {
    "summarize_youtube": _impl_summarize_youtube,
    "search_report": _impl_search_report,
    "fetch_analyst_reports": _impl_fetch_analyst_reports,
    "screen_stocks": _impl_screen_stocks,
}


def run_content_tool(name: str, args: dict, *, user=None, db=None) -> str:
    """콘텐츠 툴 실행 → LLM 되먹임용 문자열. 미등록·예외는 안전 메시지(챗 안 죽임).

    user/db 는 KIS client 가 필요한 툴(screen_stocks)로 관통(프로덕션 __shared__ DB 키). 나머지 툴은 무시.
    """
    impl = _TOOL_IMPL.get(name)
    if impl is None:
        return "요청을 처리할 수 없습니다."
    try:
        return impl(args or {}, user=user, db=db)
    except Exception:
        return "콘텐츠를 불러오는 중 문제가 발생했습니다."


# ── 뷰 컨텍스트 툴(표시 팝업 + 현재 화면 데이터 즉답 겸용, P2) ──────────────────
# show_balance/show_watchlist/show_stock_report 는 여전히 popups(프론트가 패널 표시)로 가되,
# chat.py 가 tool 결과에 서버 조회 스냅샷 요약을 함께 실어 같은 턴에 LLM 이 즉답하게 한다.
# CONTENT_TOOLS 와 별개(콘텐츠 툴은 popups 제외, 뷰 툴은 popups 유지).
VIEW_CONTEXT_TOOLS = frozenset({"show_balance", "show_watchlist", "show_stock_report"})


def view_context_kind_args(name: str, args: dict) -> tuple[str, dict] | None:
    """뷰 컨텍스트 툴명+args → build_view_context(kind, args) 입력. 대상 아니면 None."""
    if name not in VIEW_CONTEXT_TOOLS:
        return None
    args = args or {}
    if name == "show_balance":
        return ("balance", {})
    if name == "show_watchlist":
        return ("watchlist", {})
    # show_stock_report → ticker/종목명 전달(경량 시세 + 애널리스트 스냅샷).
    return ("stock_report", {"ticker": args.get("ticker"), "stock_name": args.get("stock_name")})
