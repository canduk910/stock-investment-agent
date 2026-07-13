"""CombinedAnalystSummary — 여러 증권사 애널리스트 리포트 '종합 요약'의 구조·안전 계약(항목5).

AnalystReportSummary(chat/analyst_schema.py) 패턴 재사용. 차이: **여러 리포트를 가로질러 종합**한
결과라 개별 목표주가/투자의견 대신 '의견분포'(리포트 의견 집계)·'목표주가범위'를 담고, 본문은
**종합요약(최대 10줄)** 리스트로 압축한다. 이건 **여러 증권사 리포트 내용의 종합·인용**이지
에이전트의 매수/매도 판정이 아니다 — 출처 복수 귀속·면책을 프롬프트+스키마로 강제한다.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from chat.report_schema import NonEmptyStr  # 비어있지 않은 문자열(리스트 원소용)


class CombinedAnalystSummary(BaseModel):
    """LLM 이 최근 N개 리포트 요약을 종합한 구조화 결과(리포트 인용, 판정 아님)."""

    종목: str = Field(min_length=1)
    # 리포트별 투자의견 집계(예 "매수 2·중립 1") — 리포트가 밝힌 의견의 분포(출처 귀속, 에이전트 판정 아님).
    의견분포: str = Field(min_length=1)
    # 리포트 목표주가들의 범위(예 "5.0만원~5.5만원"). 리포트에 없으면 null.
    목표주가범위: str | None = None
    # 종합 본문 — 최대 10줄로 압축(각 줄 짧은 한 문장). 최소 1(빈 종합 방지)·최대 10.
    종합요약: list[NonEmptyStr] = Field(min_length=1, max_length=10)
    # 면책 필수 — "여러 증권사 리포트 내용·자문 아님" 고지 실효성.
    면책고지: str = Field(min_length=1)
