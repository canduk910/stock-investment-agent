"""LLM 구조화 요약 공통 코어 — report·analyst_report·market_outlook·analyst_combined 공유.

4개 summarizer 가 각자 구현하던 동일 패턴을 단일 출처로 통합한다:
  make_client → request_json(response_format=json_object + CHAT_MODEL_PARAMS)
  → parse_and_validate(schema) → 검증 실패 시 1회 재요청 → None.

각 모듈은 **프롬프트 빌더와 반환 dict shape 를 자기가 소유**한다(report 의 quant_summary·
combined 의 report_count 등 도메인차 보존). 여기서는 검증된 모델 or None 만 돌려주고,
폴백 dict 조립은 호출부가 한다. 판정은 코드·LLM 은 요약(설명)만 — 안전 원칙 불변.
"""
from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from chat.tools import CHAT_MODEL, CHAT_MODEL_PARAMS

T = TypeVar("T", bound=BaseModel)


def make_client():
    """OpenAI 클라이언트 단일 출처(키는 infra.config 에서만). 테스트는 client 를 주입한다."""
    from openai import OpenAI

    from infra.config import openai_api_key

    return OpenAI(api_key=openai_api_key())


def request_json(client, prompt: str) -> str:
    """CHAT_MODEL 에 JSON 1회 요청 → content 문자열(빈 응답은 ''). CHAT_MODEL_PARAMS 자동 병합."""
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "system", "content": prompt}],
        response_format={"type": "json_object"},
        **CHAT_MODEL_PARAMS,
    )
    return resp.choices[0].message.content or ""


def parse_and_validate(content: str, schema_class: type[T]) -> T | None:
    """content(JSON) → schema 검증 모델. 파싱·검증 실패는 None(폴백 판단은 호출부)."""
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    try:
        return schema_class(**data)
    except (ValidationError, TypeError):
        return None


def generate_validated(client, prompt: str, schema_class: type[T]) -> T | None:
    """request_json → parse_and_validate, 검증 실패 시 1회 재요청(총 2회). OpenAI 예외·2회 실패는 None.

    반환 dict shape 는 도메인마다 달라 호출부가 만든다 — 여기선 검증된 모델 or None 만.
    """
    for _ in range(2):  # 최초 + 검증 실패 시 1회 재요청
        try:
            content = request_json(client, prompt)
        except Exception:
            return None  # OpenAI 예외 → 폴백(크래시 금지)
        obj = parse_and_validate(content, schema_class)
        if obj is not None:
            return obj
    return None
