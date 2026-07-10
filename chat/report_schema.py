"""StockReport Pydantic 스키마 — llm-safety-guide §4 (P2). 안전요건을 타입으로 강제.

이 스키마의 존재 이유: 안전 요건을 '프롬프트 지시'가 아니라 '검증 실패'로 강제한다.
지시("리스크를 반드시 1개 이상 써라")는 LLM 이 어길 수 있지만, 검증 실패는 재시도되고
그래도 안 되면 폴백된다(chat/report.py). 즉 안전을 타입 시스템으로 못박는다:

- 종합의견 Literal["긍정적","중립","신중"] — "매수/매도" 명령형 라벨을 타입에서 원천 배제.
- 리스크요인 min_length=1 + 원소 비어있지 않음 — 장밋빛 리포트·['']위장 방지(리스크 최소 1개 강제).
- 투자포인트·리스크요인 max_length=3 — 과대 나열 방지.
- 요약·국면정합성·면책고지 min_length=1 — 누락뿐 아니라 **빈 문자열도** 검증 실패(고지 실효성 담보).
  (다만 화면 면책 고지는 프론트 코드고정 상수가 SSOT라 LLM 산출과 무관하게 항상 노출된다.)

필드명은 한글 그대로 유지한다(프론트 렌더·report_store 가 이 키로 소비 — 계약).
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

# 종합의견 허용 라벨 단일 출처 — 프론트 종합의견 배지 매핑(reportFormat.js)과 일치해야 함.
# 매수/매도류 명령형 라벨은 이 집합에 넣지 않는다(안전: 타입에서 원천 배제).
OPINION_VALUES = ("긍정적", "중립", "신중")

# 비어있지 않은 문자열(리스트 원소용) — 리스크요인 [''] 처럼 빈 항목으로 위장한 값 거부(IMP-14).
NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]


class StockReport(BaseModel):
    """LLM 이 생성하는 종목 서술 리포트의 구조·안전 계약.

    정량 판정(밸류에이션·CAGR·국면 게이트)은 이미 코드가 확정했고, 이 스키마는 그 결과를
    '설명한' LLM 산출을 담되 안전 제약(enum·개수·필수)을 검증으로 강제한다.
    """

    종합의견: Literal["긍정적", "중립", "신중"]
    # 필수 문자열은 min_length=1 — 키만 있고 비어있는(예: 면책고지="") 값도 검증 실패시킨다(IMP-14).
    요약: str = Field(min_length=1)
    투자포인트: list[NonEmptyStr] = Field(default_factory=list, max_length=3)
    # 리스크요인은 최소 1개 강제 + 원소도 비어있지 않아야(['']로 위장 방지) — 장밋빛 리포트 방지.
    리스크요인: list[NonEmptyStr] = Field(min_length=1, max_length=3)
    국면정합성: str = Field(min_length=1)
    # 면책고지 필수·비어있지 않아야 — "참고용·면허 있는 자문 아님" 상시 고지의 실효성 담보.
    면책고지: str = Field(min_length=1)
