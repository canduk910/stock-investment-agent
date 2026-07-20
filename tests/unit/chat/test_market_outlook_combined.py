"""시황 최근 5개 종합 '금일의 요약' — 스키마 안전강제 + 생성·폴백·최근 5개 제한.

저장된 per-report 요약(store.list_reports)만으로 LLM 종합(PDF 재다운로드 없음). 시장 전체(ticker 없음).
안전: 여러 시황 리포트 내용의 종합·인용(시장 판정 아님)·복수 출처 귀속·면책.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from chat.market_outlook_combined import summarize_recent_outlooks
from chat.market_outlook_combined_schema import CombinedMarketOutlookSummary

_VALID = {
    "시장전망분포": "중립 3·신중 2",
    "종합요약": ["외국인 수급 개선", "실적 시즌 기대", "환율 변동성 유의"],
    "면책고지": "이 종합은 여러 증권사 시황 리포트 내용이며 투자 판단·매매 권유가 아니다.",
}


def _entry(broker, stance, *, date="26.07.20"):
    """저장 store 레코드 shape — summary dict 포함(ticker 없음)."""
    return {
        "report_id": f"nid-{broker}", "broker": broker, "title": f"{broker} 시황", "date": date,
        "pdf_url": "https://x/r.pdf",
        "summary": {
            "증권사": broker, "제목": f"{broker} 시황", "시장전망": stance, "요약": "박스권.",
            "세줄요약": ["a", "b", "c"], "핵심요지": ["금리"], "리스크요인": ["환율"],
            "면책고지": "리포트 인용·자문 아님.",
        },
        "created_at": "2026-07-20T00:00:00+00:00",
    }


class _StubStore:
    def __init__(self, reports):
        self._reports = reports

    def list_reports(self):  # ticker 없음(시장 전체)
        return list(self._reports)


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
    s = CombinedMarketOutlookSummary(**_VALID)
    assert s.시장전망분포 == "중립 3·신중 2" and len(s.종합요약) == 3


def test_schema_requires_시장전망분포():
    with pytest.raises(ValidationError):
        CombinedMarketOutlookSummary(**{**_VALID, "시장전망분포": ""})


def test_schema_rejects_empty_종합요약():
    with pytest.raises(ValidationError):
        CombinedMarketOutlookSummary(**{**_VALID, "종합요약": []})


def test_schema_종합요약_max_10():
    with pytest.raises(ValidationError):
        CombinedMarketOutlookSummary(**{**_VALID, "종합요약": [f"줄{i}" for i in range(11)]})


def test_schema_requires_면책():
    with pytest.raises(ValidationError):
        CombinedMarketOutlookSummary(**{**_VALID, "면책고지": ""})


# ── 생성·폴백 ──
def test_summarize_valid():
    store = _StubStore([_entry("KB증권", "중립"), _entry("삼성증권", "신중")])
    client = _FakeClient([json.dumps(_VALID)])
    out = summarize_recent_outlooks(store=store, client=client)
    assert out["validation_failed"] is False
    assert out["summary"]["시장전망분포"] == "중립 3·신중 2"
    assert out["report_count"] == 2
    assert client.calls[0]["reasoning_effort"] == "none"  # CHAT_MODEL_PARAMS 병합


def test_summarize_no_reports_fallback():
    # 저장된 시황 0개 → LLM 미호출 + 폴백.
    store = _StubStore([])
    client = _FakeClient([])
    out = summarize_recent_outlooks(store=store, client=client)
    assert out["validation_failed"] is True and out["report_count"] == 0
    assert client.calls == []


def test_summarize_invalid_falls_back():
    store = _StubStore([_entry("KB증권", "중립")])
    client = _FakeClient(["not json", "still bad"])
    out = summarize_recent_outlooks(store=store, client=client)
    assert out["validation_failed"] is True and len(client.calls) == 2


def test_summarize_uses_only_recent_5():
    # 8개 저장 → 최근 5개만 종합(list_reports 는 date 내림차순).
    store = _StubStore([_entry(f"증권{i}", "중립") for i in range(8)])
    client = _FakeClient([json.dumps(_VALID)])
    out = summarize_recent_outlooks(store=store, client=client)
    assert out["report_count"] == 5
