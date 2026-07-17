"""LLM 구조화 요약 공통 코어 테스트 — 4 summarizer 가 공유하는 request/validate/retry.

라이브 미호출: FakeClient 를 주입해 create() 시퀀스를 제어. 검증 대상은 결정적 부분
(파싱·검증·1회 재시도·예외→None·요청 파라미터). 각 도메인 반환 shape 은 모듈 테스트가 커버.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from pydantic import BaseModel, Field

from chat.structured_summary import generate_validated, parse_and_validate, request_json


class _Schema(BaseModel):
    name: str = Field(min_length=1)
    n: int


class _FakeClient:
    """create() 가 미리 준 content 시퀀스를 순서대로 반환. 호출 인자를 calls 에 기록."""

    def __init__(self, contents):
        self._contents = list(contents)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        content = self._contents.pop(0)  # 부족하면 IndexError → 과다호출 감지
        msg = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class _Boom:
    def __init__(self):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._boom))

    def _boom(self, **kw):
        raise RuntimeError("openai down")


_VALID = json.dumps({"name": "삼성", "n": 3})


def test_parse_and_validate_valid():
    obj = parse_and_validate(_VALID, _Schema)
    assert obj is not None and obj.name == "삼성" and obj.n == 3


def test_parse_and_validate_bad_json_is_none():
    assert parse_and_validate("not json", _Schema) is None


def test_parse_and_validate_schema_violation_is_none():
    # name 빈 문자열(min_length=1 위반) → None(안전강제).
    assert parse_and_validate(json.dumps({"name": "", "n": 1}), _Schema) is None


def test_request_json_includes_model_params():
    client = _FakeClient([_VALID])
    request_json(client, "prompt")
    call = client.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    assert call["reasoning_effort"] == "none"  # CHAT_MODEL_PARAMS 병합(추론형 필수)
    assert call["messages"][0]["role"] == "system"


def test_generate_validated_first_try():
    client = _FakeClient([_VALID])
    obj = generate_validated(client, "p", _Schema)
    assert obj is not None and obj.n == 3
    assert len(client.calls) == 1


def test_generate_validated_retries_once_then_succeeds():
    client = _FakeClient(["bad json", _VALID])
    obj = generate_validated(client, "p", _Schema)
    assert obj is not None
    assert len(client.calls) == 2  # 1회 재요청


def test_generate_validated_two_failures_is_none():
    client = _FakeClient(["bad", "still bad"])
    assert generate_validated(client, "p", _Schema) is None
    assert len(client.calls) == 2  # 재요청까지 하고 포기


def test_generate_validated_openai_exception_is_none():
    assert generate_validated(_Boom(), "p", _Schema) is None
