"""네이버 애널리스트 리포트 → 구조화 요약 생성(chat/report.py 패턴 재사용).

PDF 원문 텍스트(rag.ingest.extract_text) + 메타(증권사·종목·제목·작성일)를 컨텍스트로
CHAT_MODEL 에 JSON 요약을 요청 → AnalystReportSummary 검증 → 실패 1회 재요청 → 폴백.
안전: 이건 '리포트의 내용을 요약'하는 것 — 에이전트 자체 매수/매도 판정이 아니라 출처 귀속·면책.
"""
from __future__ import annotations

import json

from pydantic import ValidationError

from chat.analyst_schema import AnalystReportSummary
from chat.tools import CHAT_MODEL, CHAT_MODEL_PARAMS

# 요약 컨텍스트로 넣을 원문 상한(프롬프트 예산). 애널리스트 리포트는 보통 2~5쪽.
_MAX_TEXT_CHARS = 8000
_FALLBACK_MESSAGE = "리포트 요약을 생성하지 못했습니다."


def _make_client():
    from openai import OpenAI

    from infra.config import openai_api_key

    return OpenAI(api_key=openai_api_key())


def _build_summary_prompt(text: str, meta: dict) -> str:
    m = meta or {}
    return f"""너는 증권사 애널리스트 리포트를 '요약'하는 도우미다. 아래 리포트 원문을 읽고 JSON 으로 요약하라.

[리포트 메타] 증권사={m.get('broker', '')} · 종목={m.get('stock_name', '')}({m.get('stock_code', '')}) · 제목={m.get('title', '')} · 작성일={m.get('date', '')}

[리포트 원문(발췌)]
{(text or '')[:_MAX_TEXT_CHARS]}

[규칙 — 반드시 지켜라]
- 이건 해당 증권사 애널리스트의 의견이다. **네 자신의 매수/매도 판정이 아니라, "리포트가 밝힌" 내용을 그대로 요약·인용**한다.
- 목표주가·투자의견은 리포트에 적힌 값 그대로. 목표주가가 없으면 null, 투자의견이 없으면 "명시 없음".
- 핵심요지 1~5개(리포트의 논지·근거). 리스크요인 1~5개 — 리포트에 리스크가 없으면 ["리포트에 명시된 리스크 없음"].
- 면책고지에는 "이 요약은 해당 증권사 리포트의 내용이며 투자 판단·매매 권유가 아니다. 참고용이며 면허 있는 투자자문이 아니다."를 담아라.
- JSON 키(한글): 증권사, 종목, 목표주가, 투자의견, 요약, 핵심요지(문자열 배열), 리스크요인(문자열 배열), 면책고지.

JSON 객체 하나만 출력하라."""


def _request(client, prompt: str) -> str:
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "system", "content": prompt}],
        response_format={"type": "json_object"},
        **CHAT_MODEL_PARAMS,
    )
    return resp.choices[0].message.content or ""


def _parse_and_validate(content: str) -> AnalystReportSummary | None:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    try:
        return AnalystReportSummary(**data)
    except (ValidationError, TypeError):
        return None


def format_report_context(entry: dict) -> str:
    """저장된 리포트 entry(메타+summary dict) → 챗 세션 핀 컨텍스트용 사람가독 텍스트.

    프론트가 요약 본문을 신뢰전송하지 않는다 — 서버가 store 에서 조회한 entry 로 만든다
    (환각·조작 차단). summary 가 없으면 메타만으로 최소 블록.
    """
    s = entry.get("summary") or {}
    broker = s.get("증권사") or entry.get("broker", "")
    stock = s.get("종목") or entry.get("stock_name", "")
    lines = [f"- 증권사: {broker}", f"- 종목: {stock}"]
    if entry.get("date"):
        lines.append(f"- 작성일: {entry['date']}")
    if s.get("목표주가"):
        lines.append(f"- 리포트 목표주가: {s['목표주가']}")
    if s.get("투자의견"):
        lines.append(f"- 리포트 투자의견(리포트가 밝힌 의견): {s['투자의견']}")
    if s.get("요약"):
        lines.append(f"- 요약: {s['요약']}")
    for k in ("핵심요지", "리스크요인"):
        vals = s.get(k) or []
        if vals:
            lines.append(f"- {k}: " + " / ".join(str(v) for v in vals))
    if s.get("면책고지"):
        lines.append(f"- 면책: {s['면책고지']}")
    return "\n".join(lines)


def summarize_report(text: str, meta: dict, *, client=None) -> dict:
    """리포트 원문 텍스트 → {summary|None, validation_failed}. 항상 dict(크래시 없음).

    빈 텍스트·검증 실패·OpenAI 예외는 validation_failed=True(폴백).
    """
    if not text or not text.strip():
        return {"summary": None, "validation_failed": True, "message": _FALLBACK_MESSAGE}
    if client is None:
        client = _make_client()
    prompt = _build_summary_prompt(text, meta)
    for _ in range(2):  # 최초 + 검증 실패 시 1회 재요청
        try:
            content = _request(client, prompt)
        except Exception:
            break  # OpenAI 예외 → 폴백(크래시 금지)
        summary = _parse_and_validate(content)
        if summary is not None:
            return {"summary": summary.model_dump(), "validation_failed": False}
    return {"summary": None, "validation_failed": True, "message": _FALLBACK_MESSAGE}
