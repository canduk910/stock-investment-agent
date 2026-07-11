"""AnalystReportSummary — 네이버 애널리스트 리포트 '보고서별 요약'의 구조·안전 계약.

StockReport(chat/report_schema.py) 패턴 재사용: 안전 요건을 '프롬프트 지시'가 아니라
'검증 실패'로 강제한다(실패는 재시도·폴백). 단 이건 **에이전트의 판정이 아니라 해당 증권사
리포트의 내용을 요약·인용**하는 것이라 투자의견은 Literal 로 가두지 않고(리포트가 밝힌 값 그대로),
대신 '출처 귀속·면책'을 프롬프트+표시로 강제한다. 필드 한글 키는 프론트 렌더·store 소비 계약.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from chat.report_schema import NonEmptyStr  # 비어있지 않은 문자열(리스트 원소용, [''] 위장 방지)


class AnalystReportSummary(BaseModel):
    """LLM 이 애널리스트 리포트 원문에서 뽑은 구조화 요약."""

    증권사: str = Field(min_length=1)
    종목: str = Field(min_length=1)
    목표주가: str | None = None  # 리포트에 없으면 null(숫자/범위/텍스트 모두 문자열로)
    # 리포트가 밝힌 투자의견(매수/Hold 등) — 에이전트 자체 판정이 아니라 '리포트의 의견'(귀속).
    투자의견: str = Field(min_length=1)
    요약: str = Field(min_length=1)
    # 핵심요지·리스크는 최소 1개 강제(원소 비어있지 않음) — 리스크 누락(장밋빛) 방지, 과대나열 상한.
    핵심요지: list[NonEmptyStr] = Field(min_length=1, max_length=5)
    리스크요인: list[NonEmptyStr] = Field(min_length=1, max_length=5)
    # 면책 필수·비어있지 않아야 — "리포트 내용·자문 아님" 고지 실효성.
    면책고지: str = Field(min_length=1)
