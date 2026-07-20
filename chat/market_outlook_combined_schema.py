"""CombinedMarketOutlookSummary — 여러 증권사 시황(매크로) 리포트 '종합 요약'의 구조·안전 계약.

CombinedAnalystSummary(chat/analyst_combined_schema.py) 패턴 재사용. 차이: 시황은 **시장 전체**라
종목·목표주가가 없고, 개별 투자의견 대신 '시장전망분포'(리포트 시장전망 집계)를 담는다. 본문은
**종합요약(최대 10줄)** 리스트로 중복 제거·압축. 이건 **여러 증권사 시황 리포트 내용의 종합·인용**이지
에이전트의 시장 판정이 아니다 — 출처 복수 귀속·면책을 프롬프트+스키마로 강제한다.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from chat.report_schema import NonEmptyStr  # 비어있지 않은 문자열(리스트 원소용)


class CombinedMarketOutlookSummary(BaseModel):
    """LLM 이 최근 N개 시황 리포트 요약을 종합한 구조화 결과(리포트 인용, 판정 아님)."""

    # 리포트별 시장전망 집계(예 "중립 3·신중 2") — 리포트가 밝힌 전망의 분포(출처 귀속, 에이전트 판정 아님).
    시장전망분포: str = Field(min_length=1)
    # 종합 본문 — 중복 제거 후 최대 10줄로 압축(각 줄 짧은 한 문장). 최소 1(빈 종합 방지)·최대 10.
    종합요약: list[NonEmptyStr] = Field(min_length=1, max_length=10)
    # 면책 필수 — "여러 증권사 시황 리포트 내용·자문 아님" 고지 실효성.
    면책고지: str = Field(min_length=1)

    @field_validator("시장전망분포", mode="before")
    @classmethod
    def _coerce_distribution(cls, v):
        """LLM 이 분포를 문자열 대신 dict/list 로 낼 때가 있다(시장전망이 긴 문단이면 버킷 집계를
        객체로 출력). 컴팩트 문자열(예 "중립 3 · 신중 2")로 강제해 검증 실패를 막는다(방어)."""
        if isinstance(v, dict):
            return " · ".join(f"{k} {v[k]}" for k in v) or "전망 명시 없음"
        if isinstance(v, (list, tuple)):
            return " · ".join(str(x) for x in v) or "전망 명시 없음"
        return v
