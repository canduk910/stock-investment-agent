"""시황(매크로) 리포트 최근 N개 종합 '금일의 요약' 생성 — chat/analyst_combined.py 패턴 재사용.

저장된 per-report 요약(store.list_reports(), date 내림차순 최신순)만으로 LLM 이 종합한다 —
**PDF 재다운로드·재수집 없음**(0 네이버, 1 LLM). 여러 시황 리포트를 종합·**중복 제거**해 최대 10줄
핵심메시지로 압축한다. CHAT_MODEL 에 JSON 종합 요청 → CombinedMarketOutlookSummary 검증 →
실패 1회 재요청 → 폴백. 안전: 여러 리포트 내용의 종합·인용(시장 판정 아님) — 복수 출처 귀속·면책 강제.
"""
from __future__ import annotations

from chat.market_outlook import format_market_outlook_context  # 저장 entry → 가독 컨텍스트(재사용)
from chat.market_outlook_combined_schema import CombinedMarketOutlookSummary
from chat.structured_summary import generate_validated, make_client

_DEFAULT_LIMIT = 5  # "최근 5개" 시황 종합(사용자 요구)
_NO_REPORTS_MESSAGE = "종합할 저장된 시황 리포트가 없습니다. 먼저 시황을 가져오세요."
_FALLBACK_MESSAGE = "시황 종합요약을 생성하지 못했습니다."


def _build_combined_prompt(reports: list[dict]) -> str:
    """최근 시황 리포트들의 저장 요약을 컴팩트 컨텍스트로 조립 → 종합·중복제거 지시 프롬프트."""
    blocks = [f"[리포트 {i}]\n{format_market_outlook_context(e)}" for i, e in enumerate(reports, 1)]
    joined = "\n\n".join(blocks)
    return f"""너는 여러 증권사 시황(매크로) 리포트를 '종합'하는 도우미다. 아래 시황 요약들을 읽고 JSON 으로 종합·요약하라.

[최근 시황 리포트 요약들]
{joined}

[규칙 — 반드시 지켜라]
- 이건 **여러 증권사 시황 리포트의 내용을 종합·인용**하는 것이다. **네 자신의 시장 판정이 아니라, "여러 리포트에 따르면" 식으로 출처를 복수 귀속**해 종합한다.
- 종합요약: 위 시황들을 **최대 10줄**로 종합하라(각 줄 짧은 한 문장, 최소 1개·최대 10개). **중복되는 메시지는 하나로 합쳐 제거**하고, 공통된 시장 인식·근거를 우선하되 리포트 간 이견이 있으면 함께 밝혀라.
- 시장전망분포: 리포트별 시장전망을 집계해 분포로 표현하라(예 "중립 3·신중 2"). 리포트가 밝힌 전망만 세고, 없으면 "전망 명시 없음".
- 특정 종목 추천·매수/매도를 단정하지 말고, 근거 없는 숫자를 지어내지 마라(위 리포트에 있는 내용만).
- 면책고지에는 "이 종합은 여러 증권사 시황 리포트의 내용이며 투자 판단·매매 권유가 아니다. 참고용이며 면허 있는 투자자문이 아니다."를 담아라.
- JSON 키(한글): 시장전망분포, 종합요약(문자열 배열, 최대 10), 면책고지.

JSON 객체 하나만 출력하라."""


def summarize_recent_outlooks(*, limit: int = _DEFAULT_LIMIT, client=None, store=None) -> dict:
    """최근 limit개(기본 5) 저장 시황 요약 → 종합 '금일의 요약'. 항상 dict(크래시 없음).

    반환: {summary|None, validation_failed, report_count[, message]}.
    0개면 LLM 미호출 + 폴백. 검증 실패·OpenAI 예외는 1회 재시도 후 폴백. `report_count`는 코드가 계산
    (LLM 카운트 환각 방지).
    """
    if store is None:
        from chat.market_outlook_store import default_store

        store = default_store()
    reports = (store.list_reports() or [])[:limit]  # ticker 없음(시장 전체)
    count = len(reports)
    if count == 0:
        return {
            "summary": None,
            "validation_failed": True,
            "message": _NO_REPORTS_MESSAGE,
            "report_count": 0,
        }
    if client is None:
        client = make_client()
    prompt = _build_combined_prompt(reports)
    summary = generate_validated(client, prompt, CombinedMarketOutlookSummary)
    if summary is not None:
        return {"summary": summary.model_dump(), "validation_failed": False, "report_count": count}
    return {
        "summary": None,
        "validation_failed": True,
        "message": _FALLBACK_MESSAGE,
        "report_count": count,
    }
