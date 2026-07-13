"""애널리스트 리포트 최근 N개 종합 요약 생성(항목5) — chat/market_outlook.py 패턴 재사용.

저장된 per-report 요약(store.list_reports(ticker), date 내림차순 최신순)만으로 LLM 이 종합한다
— **PDF 재다운로드·재수집 없음**(0 네이버/KIS, 1 LLM). CHAT_MODEL 에 JSON 종합을 요청 →
CombinedAnalystSummary 검증 → 실패 1회 재요청 → 폴백. 안전: 여러 증권사 리포트 내용의 종합·인용
(에이전트 매수/매도 판정 아님) — 복수 출처 귀속·면책을 프롬프트+스키마로 강제.
"""
from __future__ import annotations

import json

from pydantic import ValidationError

from chat.analyst_combined_schema import CombinedAnalystSummary
from chat.analyst_report import format_report_context  # 저장 entry → 가독 컨텍스트(재사용)
from chat.tools import CHAT_MODEL, CHAT_MODEL_PARAMS

_DEFAULT_LIMIT = 3  # "최근 3개" 종합(사용자 요구)
_NO_REPORTS_MESSAGE = "종합할 저장된 리포트가 없습니다. 먼저 이 종목 리포트를 가져오세요."
_FALLBACK_MESSAGE = "리포트 종합요약을 생성하지 못했습니다."


def _make_client():
    from openai import OpenAI

    from infra.config import openai_api_key

    return OpenAI(api_key=openai_api_key())


def _report_name(reports: list[dict], ticker: str) -> str:
    for entry in reports:
        s = entry.get("summary") or {}
        name = s.get("종목") or entry.get("stock_name")
        if name:
            return str(name)
    return ticker


def _build_combined_prompt(reports: list[dict], ticker: str) -> str:
    """최근 리포트들의 저장 요약을 컴팩트 컨텍스트로 조립 → 종합 지시 프롬프트."""
    name = _report_name(reports, ticker)
    blocks = []
    for i, entry in enumerate(reports, 1):
        blocks.append(f"[리포트 {i}]\n{format_report_context(entry)}")
    joined = "\n\n".join(blocks)
    return f"""너는 여러 증권사 애널리스트 리포트를 '종합'하는 도우미다. 아래 리포트 요약들을 읽고 JSON 으로 종합·요약하라.

[대상 종목] {name} ({ticker})

[최근 리포트 요약들]
{joined}

[규칙 — 반드시 지켜라]
- 이건 **여러 증권사 리포트의 내용을 종합·인용**하는 것이다. **네 자신의 매수/매도 판정이 아니라, "여러 리포트에 따르면" 식으로 출처를 복수 귀속**해 종합한다.
- 종합요약: 위 리포트들을 **최대 10줄**로 종합하라(각 줄 짧은 한 문장, 정확히 10개 이하·최소 1개). 공통된 논지·근거를 우선하되 리포트 간 이견이 있으면 함께 밝혀라.
- 의견분포: 리포트별 투자의견을 집계해 분포로 표현하라(예 "매수 2·중립 1"). 리포트가 밝힌 의견만 세고, 없으면 "의견 명시 없음".
- 목표주가범위: 리포트 목표주가들의 범위(예 "5.0만원~5.5만원"). 목표주가가 하나도 없으면 null.
- 매수/매도를 단정하지 말고, 근거 없는 숫자를 지어내지 마라(위 리포트에 있는 값만).
- 면책고지에는 "이 종합은 여러 증권사 리포트의 내용이며 투자 판단·매매 권유가 아니다. 참고용이며 면허 있는 투자자문이 아니다."를 담아라.
- JSON 키(한글): 종목, 의견분포, 목표주가범위, 종합요약(문자열 배열, 최대 10), 면책고지.

JSON 객체 하나만 출력하라."""


def _request(client, prompt: str) -> str:
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "system", "content": prompt}],
        response_format={"type": "json_object"},
        **CHAT_MODEL_PARAMS,
    )
    return resp.choices[0].message.content or ""


def _parse_and_validate(content: str) -> CombinedAnalystSummary | None:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    try:
        return CombinedAnalystSummary(**data)
    except (ValidationError, TypeError):
        return None


def summarize_recent_reports(
    ticker: str, *, limit: int = _DEFAULT_LIMIT, client=None, store=None
) -> dict:
    """최근 limit개(기본 3) 저장 리포트 요약 → 종합. 항상 dict(크래시 없음).

    반환: {summary|None, validation_failed, report_count[, message]}.
    0개면 LLM 미호출 + 폴백. 검증 실패·OpenAI 예외는 1회 재시도 후 폴백.
    """
    if store is None:
        from chat.analyst_store import default_store

        store = default_store()
    reports = (store.list_reports(ticker) or [])[:limit]
    count = len(reports)
    if count == 0:
        return {
            "summary": None,
            "validation_failed": True,
            "message": _NO_REPORTS_MESSAGE,
            "report_count": 0,
        }
    if client is None:
        client = _make_client()
    prompt = _build_combined_prompt(reports, ticker)
    for _ in range(2):  # 최초 + 검증 실패 시 1회 재요청
        try:
            content = _request(client, prompt)
        except Exception:
            break  # OpenAI 예외 → 폴백(크래시 금지)
        summary = _parse_and_validate(content)
        if summary is not None:
            return {
                "summary": summary.model_dump(),
                "validation_failed": False,
                "report_count": count,
            }
    return {
        "summary": None,
        "validation_failed": True,
        "message": _FALLBACK_MESSAGE,
        "report_count": count,
    }
