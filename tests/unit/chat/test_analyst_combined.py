"""애널리스트 리포트 최근 3개 종합 10줄요약(항목5) — 스키마 안전강제 + 생성·폴백.

저장된 per-report 요약(store.list_reports)만으로 LLM 이 종합한다(PDF 재다운로드 없음).
안전: 여러 증권사 리포트 내용의 **종합·인용**(에이전트 판정 아님)·복수 출처 귀속·면책.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import chat.analyst_combined as ac
from chat.analyst_combined import summarize_recent_reports
from chat.analyst_combined_schema import CombinedAnalystSummary


_VALID = {
    "종목": "GS건설",
    "의견분포": "매수 2·중립 1",
    "목표주가범위": "5.0만원~5.5만원",
    "종합요약": ["실적 개선 기대", "수주 회복 흐름", "밸류에이션 부담 완화"],
    "면책고지": "이 종합은 여러 증권사 리포트 내용이며 투자 판단·매매 권유가 아니다.",
}


def _entry(broker, opinion, target, *, date="26.07.10"):
    """저장 store 레코드 shape(report_repo._entry_from_row) — summary dict 포함."""
    return {
        "report_id": f"nid-{broker}", "broker": broker, "stock_name": "GS건설",
        "title": f"{broker} 리포트", "date": date, "pdf_url": "https://x/r.pdf",
        "summary": {
            "증권사": broker, "종목": "GS건설", "목표주가": target, "투자의견": opinion,
            "요약": "실적 개선.", "핵심요지": ["수주 회복"], "리스크요인": ["원가 상승"],
            "면책고지": "리포트 인용·자문 아님.",
        },
        "created_at": "2026-07-10T00:00:00+00:00",
    }


class _StubStore:
    def __init__(self, reports):
        self._reports = reports

    def list_reports(self, ticker):
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
    s = CombinedAnalystSummary(**_VALID)
    assert s.종목 == "GS건설" and len(s.종합요약) == 3


def test_schema_requires_의견분포():
    with pytest.raises(ValidationError):
        CombinedAnalystSummary(**{**_VALID, "의견분포": ""})


def test_schema_목표주가범위_optional():
    s = CombinedAnalystSummary(**{**_VALID, "목표주가범위": None})
    assert s.목표주가범위 is None


def test_schema_rejects_empty_종합요약():
    with pytest.raises(ValidationError):
        CombinedAnalystSummary(**{**_VALID, "종합요약": []})


def test_schema_종합요약_max_10():
    with pytest.raises(ValidationError):
        CombinedAnalystSummary(**{**_VALID, "종합요약": [f"줄{i}" for i in range(11)]})


def test_schema_requires_면책():
    with pytest.raises(ValidationError):
        CombinedAnalystSummary(**{**_VALID, "면책고지": ""})


# ── 생성·폴백 ──
def test_summarize_valid():
    store = _StubStore([_entry("KB증권", "매수", "5.5만원"), _entry("삼성증권", "중립", "5.0만원")])
    client = _FakeClient([json.dumps(_VALID)])
    out = summarize_recent_reports("006360", store=store, client=client)
    assert out["validation_failed"] is False
    assert out["summary"]["의견분포"] == "매수 2·중립 1"
    assert out["report_count"] == 2
    assert client.calls[0]["reasoning_effort"] == "none"  # CHAT_MODEL_PARAMS 병합


def test_summarize_no_reports_fallback():
    # 저장된 리포트 0개 → LLM 미호출 + 폴백.
    store = _StubStore([])
    client = _FakeClient([])
    out = summarize_recent_reports("006360", store=store, client=client)
    assert out["validation_failed"] is True and out["report_count"] == 0
    assert client.calls == []


def test_summarize_invalid_falls_back():
    store = _StubStore([_entry("KB증권", "매수", "5.5만원")])
    client = _FakeClient(["not json", "still bad"])
    out = summarize_recent_reports("006360", store=store, client=client)
    assert out["validation_failed"] is True and len(client.calls) == 2


def test_summarize_uses_only_recent_3():
    # 5개 저장 → 최근 3개만 종합(store.list_reports 는 date 내림차순).
    reports = [_entry(f"증권{i}", "매수", "5만원") for i in range(5)]
    store = _StubStore(reports)
    client = _FakeClient([json.dumps(_VALID)])
    out = summarize_recent_reports("006360", store=store, client=client)
    assert out["report_count"] == 3
    # 프롬프트 컨텍스트에 3개 리포트 블록만.
    prompt = client.calls[0]["messages"][0]["content"]
    assert prompt.count("[리포트 ") == 3


def test_prompt_enforces_attribution_and_disclaimer():
    prompt = ac._build_combined_prompt([_entry("KB증권", "매수", "5.5만원")], "006360")
    assert "리포트에 따르면" in prompt or "출처" in prompt  # 복수 출처 귀속
    assert "면책" in prompt
    assert "종합요약" in prompt and ("10줄" in prompt or "10개" in prompt)


def test_summarize_no_pdf_download():
    # 저장 요약만으로 합성 — 수집/다운로드 함수를 절대 부르지 않는다(0 네이버 호출).
    import collectors.naver_research as nr

    called = {"n": 0}

    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("PDF 재다운로드 금지")

    # download_pdf/fetch_stock_reports 를 호출하면 실패하도록.
    orig_dl = getattr(nr, "download_pdf", None)
    orig_fetch = getattr(nr, "fetch_stock_reports", None)
    try:
        if orig_dl:
            nr.download_pdf = _boom
        if orig_fetch:
            nr.fetch_stock_reports = _boom
        store = _StubStore([_entry("KB증권", "매수", "5.5만원")])
        client = _FakeClient([json.dumps(_VALID)])
        out = summarize_recent_reports("006360", store=store, client=client)
        assert out["validation_failed"] is False
        assert called["n"] == 0
    finally:
        if orig_dl:
            nr.download_pdf = orig_dl
        if orig_fetch:
            nr.fetch_stock_reports = orig_fetch
