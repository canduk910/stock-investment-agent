"""네이버 시황(market outlook) 리포트 → 구조화 요약 생성(chat/analyst_report.py 패턴 재사용).

PDF 원문 텍스트(rag.ingest.extract_text) + 메타(증권사·제목·작성일)를 컨텍스트로 CHAT_MODEL 에
JSON 요약을 요청 → MarketOutlookSummary 검증 → 실패 1회 재요청 → 폴백. 안전: 이건 '시황 리포트의
내용을 요약'하는 것 — 에이전트의 시장 판정이 아니라 출처 귀속·면책. 시장 국면 판정은 코드(매크로 엔진).
"""
from __future__ import annotations

from chat.market_outlook_schema import MarketOutlookSummary
from chat.structured_summary import generate_validated, make_client

_MAX_TEXT_CHARS = 8000  # 요약 컨텍스트 원문 상한(프롬프트 예산)
_FALLBACK_MESSAGE = "시황 요약을 생성하지 못했습니다."


def _build_summary_prompt(text: str, meta: dict) -> str:
    m = meta or {}
    return f"""너는 증권사 '시황(시장 전망) 리포트'를 '요약'하는 도우미다. 아래 리포트 원문을 읽고 JSON 으로 요약하라.

[리포트 메타] 증권사={m.get('broker', '')} · 제목={m.get('title', '')} · 작성일={m.get('date', '')}

[리포트 원문(발췌)]
{(text or '')[:_MAX_TEXT_CHARS]}

[규칙 — 반드시 지켜라]
- 이건 해당 증권사의 **시장 전체 시황 전망**이다(개별 종목·목표주가 아님). **네 자신의 시장 판정이 아니라, "리포트에 따르면" 내용을 그대로 요약·인용**한다.
- 시장전망에는 리포트가 밝힌 시장 스탠스(긍정적/중립/신중 등)를 리포트 표현대로 담아라.
- 세줄요약: 리포트 시황을 **3줄**로 압축하라(각 줄 짧은 한 문장, 정확히 3개 이하·최소 1개, 리포트 내용 인용). 카드 미리보기용 핵심만.
- 핵심요지 1~5개(리포트의 시황 논지·근거). 리스크요인 1~5개 — 없으면 ["리포트에 명시된 리스크 없음"].
- 면책고지에는 "이 요약은 해당 증권사 시황 리포트의 내용이며 투자 판단·매매 권유가 아니다. 참고용이며 면허 있는 투자자문이 아니다."를 담아라.
- JSON 키(한글): 증권사, 제목, 시장전망, 요약, 세줄요약(문자열 배열, 최대 3), 핵심요지(문자열 배열), 리스크요인(문자열 배열), 면책고지.

JSON 객체 하나만 출력하라."""


def format_market_outlook_context(entry: dict) -> str:
    """저장된 시황 리포트 entry(메타+summary) → 챗 세션 핀 컨텍스트용 사람가독 텍스트.

    애널리스트의 `format_report_context` 대응 — 다만 시황은 **시장 전체**라 종목·목표주가가 없고
    '시장전망'이 있다. 프론트가 요약 본문을 신뢰전송하지 않는다(서버가 store 에서 조회한 entry 로 만듦
    → 환각·조작 차단). summary 없으면 메타만으로 최소 블록.
    """
    s = entry.get("summary") or {}
    broker = s.get("증권사") or entry.get("broker", "")
    lines = [f"- 증권사: {broker}", f"- 제목: {s.get('제목') or entry.get('title', '')}"]
    if entry.get("date"):
        lines.append(f"- 작성일: {entry['date']}")
    if s.get("시장전망"):
        lines.append(f"- 시장전망(리포트가 밝힌 시장 방향): {s['시장전망']}")
    if s.get("요약"):
        lines.append(f"- 요약: {s['요약']}")
    for k in ("핵심요지", "리스크요인"):
        vals = s.get(k) or []
        if vals:
            lines.append(f"- {k}: " + " / ".join(str(v) for v in vals))
    if s.get("면책고지"):
        lines.append(f"- 면책: {s['면책고지']}")
    return "\n".join(lines)


def build_recent_outlook_context(limit: int = 3, max_chars: int = 1500, *, store=None) -> str | None:
    """최근 저장 시황 요약 N개 → 챗 프롬프트 주입용 컨텍스트 텍스트. 없으면 None(graceful).

    시장 전반 질문(macro_view)에 **국면 판정과 함께 근거**로 실린다. 저장된 per-report 요약만
    조합하므로 **PDF 재다운로드·LLM 추가호출 0**(벡터검색 불요 — 시황은 시장 전체·최근 소수 고정).
    각 리포트는 `format_market_outlook_context` 로 포맷하고 `max_chars` 로 프롬프트 예산을 제한한다.
    """
    try:
        if store is None:
            from chat.market_outlook_store import default_store

            store = default_store()
        reports = (store.list_reports() or [])[:limit]
    except Exception:
        return None  # 조회 실패는 컨텍스트 없이 진행(graceful)
    if not reports:
        return None
    blocks = [
        f"[시황 리포트 {i}]\n{format_market_outlook_context(entry)}"
        for i, entry in enumerate(reports, 1)
    ]
    return "\n\n".join(blocks)[:max_chars]


def summarize_market_outlook(text: str, meta: dict, *, client=None) -> dict:
    """시황 리포트 원문 → {summary|None, validation_failed}. 항상 dict(크래시 없음).

    빈 텍스트·검증 실패·OpenAI 예외는 validation_failed=True(폴백).
    """
    if not text or not text.strip():
        return {"summary": None, "validation_failed": True, "message": _FALLBACK_MESSAGE}
    if client is None:
        client = make_client()
    prompt = _build_summary_prompt(text, meta)
    summary = generate_validated(client, prompt, MarketOutlookSummary)
    if summary is not None:
        return {"summary": summary.model_dump(), "validation_failed": False}
    return {"summary": None, "validation_failed": True, "message": _FALLBACK_MESSAGE}
