"""애널리스트 리포트 요약 — 스키마 안전강제 + 생성·검증·폴백(OpenAI mock)."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from chat.analyst_report import summarize_report
from chat.analyst_schema import AnalystReportSummary

_META = {"broker": "한화투자증권", "stock_name": "GS건설", "stock_code": "006360",
         "title": "확실한 투자포인트", "date": "26.07.10"}

_VALID = {
    "증권사": "한화투자증권", "종목": "GS건설", "목표주가": "5만원", "투자의견": "매수",
    "요약": "건설 실적 개선 기대.", "핵심요지": ["수주 회복", "마진 개선"],
    "리스크요인": ["원자재 가격"], "면책고지": "이 요약은 리포트 내용이며 자문이 아니다.",
}


def _resp(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class _FakeClient:
    def __init__(self, contents):
        self._c = list(contents)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        return _resp(self._c.pop(0))


# ── 스키마 안전강제 ──
def test_schema_valid():
    s = AnalystReportSummary(**_VALID)
    assert s.투자의견 == "매수" and s.목표주가 == "5만원"


def test_schema_rejects_empty_risks():
    bad = {**_VALID, "리스크요인": []}
    with pytest.raises(ValidationError):
        AnalystReportSummary(**bad)


def test_schema_rejects_empty_disclaimer():
    with pytest.raises(ValidationError):
        AnalystReportSummary(**{**_VALID, "면책고지": ""})


def test_schema_target_price_optional():
    s = AnalystReportSummary(**{**_VALID, "목표주가": None})
    assert s.목표주가 is None


# ── 생성·검증·폴백 ──
def test_summarize_valid(monkeypatch):
    client = _FakeClient([json.dumps(_VALID)])
    out = summarize_report("리포트 원문 텍스트", _META, client=client)
    assert out["validation_failed"] is False
    assert out["summary"]["증권사"] == "한화투자증권"
    assert out["summary"]["투자의견"] == "매수"
    # 모델별 필수 파라미터(reasoning_effort) 병합 확인.
    assert client.calls[0]["reasoning_effort"] == "none"
    assert client.calls[0]["response_format"] == {"type": "json_object"}


def test_summarize_empty_text_no_llm():
    client = _FakeClient([])  # 호출되면 pop IndexError → 호출 안 됨을 보장
    out = summarize_report("   ", _META, client=client)
    assert out["validation_failed"] is True
    assert client.calls == []  # 빈 텍스트는 LLM 미호출


def test_summarize_invalid_json_falls_back():
    client = _FakeClient(["not json", "still not json"])
    out = summarize_report("원문", _META, client=client)
    assert out["validation_failed"] is True and out["summary"] is None
    assert len(client.calls) == 2  # 1회 재요청


def test_summarize_schema_fail_falls_back():
    bad = json.dumps({**_VALID, "리스크요인": []})  # 리스크 없음 → 검증 실패
    client = _FakeClient([bad, bad])
    out = summarize_report("원문", _META, client=client)
    assert out["validation_failed"] is True


def test_summarize_openai_exception_falls_back():
    class _Boom:
        def __init__(self):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self._boom)
            )

        def _boom(self, **kw):
            raise Exception("openai down")

    out = summarize_report("원문", _META, client=_Boom())
    assert out["validation_failed"] is True and out["summary"] is None
