"""MarketOutlookSummary — 네이버 '시황(market outlook) 리포트' 보고서별 요약의 구조·안전 계약.

AnalystReportSummary(chat/analyst_schema.py) 패턴 재사용. 차이: 시황 리포트는 **시장 전체**를
다루므로 개별 종목·목표주가가 없다(종목·목표주가 필드 제거). 대신 '시장전망'(리포트가 밝힌 시장
스탠스)을 담는다. 이건 **해당 증권사 시황 리포트의 내용 요약·인용**이지 에이전트의 시장 판정이
아니라 출처 귀속·면책을 강제한다. 필드 한글 키는 프론트 렌더·store 소비 계약.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from chat.report_schema import NonEmptyStr  # 비어있지 않은 문자열(리스트 원소용)


class MarketOutlookSummary(BaseModel):
    """LLM 이 시황 리포트 원문에서 뽑은 구조화 요약(시장 전체, 종목 없음)."""

    증권사: str = Field(min_length=1)
    제목: str = Field(min_length=1)
    # 리포트가 밝힌 시장 스탠스(긍정적/중립/신중 등 자유 서술) — 에이전트 판정이 아니라 '리포트의 시황관'.
    시장전망: str = Field(min_length=1)
    요약: str = Field(min_length=1)
    # 컴팩트 카드용 3줄 압축 요약(항목4) — 각 줄 짧은 한 문장. 최소 1·최대 3(과밀 방지). 리포트 내용 인용.
    세줄요약: list[NonEmptyStr] = Field(min_length=1, max_length=3)
    # 핵심요지·리스크는 최소 1개 강제 — 장밋빛 일변도 방지, 과대나열 상한.
    핵심요지: list[NonEmptyStr] = Field(min_length=1, max_length=5)
    리스크요인: list[NonEmptyStr] = Field(min_length=1, max_length=5)
    # 면책 필수 — "리포트 시황 내용·자문 아님" 고지 실효성.
    면책고지: str = Field(min_length=1)
