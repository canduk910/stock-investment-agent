"""시황 요약 — 스키마 안전강제 + 생성·검증·폴백 + store idempotent + 서비스 오케스트레이션."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import chat.market_outlook as mo
import chat.market_outlook_service as svc
import collectors.naver_research as naver_research
import rag.ingest as ingest
from chat.market_outlook import summarize_market_outlook
from chat.market_outlook_schema import MarketOutlookSummary
from chat.market_outlook_store import MarketOutlookStore

_META = {"broker": "KB증권", "title": "7/10 모닝코멘트", "date": "26.07.10"}
_VALID = {
    "증권사": "KB증권", "제목": "7/10 모닝코멘트", "시장전망": "중립",
    "요약": "수급 개선 기대.", "핵심요지": ["외국인 순매수", "실적 시즌 진입"],
    "리스크요인": ["환율 변동성"], "면책고지": "이 요약은 시황 리포트 내용이며 자문이 아니다.",
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


# ── 스키마 ──
def test_schema_valid():
    s = MarketOutlookSummary(**_VALID)
    assert s.시장전망 == "중립" and s.증권사 == "KB증권"


def test_schema_no_ticker_or_target_fields():
    # 시황은 종목·목표주가 필드가 없다.
    assert "종목" not in MarketOutlookSummary.model_fields
    assert "목표주가" not in MarketOutlookSummary.model_fields


def test_schema_rejects_empty_risks():
    with pytest.raises(ValidationError):
        MarketOutlookSummary(**{**_VALID, "리스크요인": []})


def test_schema_rejects_empty_disclaimer():
    with pytest.raises(ValidationError):
        MarketOutlookSummary(**{**_VALID, "면책고지": ""})


# ── 생성·폴백 ──
def test_summarize_valid():
    client = _FakeClient([json.dumps(_VALID)])
    out = summarize_market_outlook("시황 원문", _META, client=client)
    assert out["validation_failed"] is False
    assert out["summary"]["증권사"] == "KB증권"
    assert client.calls[0]["reasoning_effort"] == "none"  # CHAT_MODEL_PARAMS 병합


def test_summarize_empty_text_no_llm():
    client = _FakeClient([])
    out = summarize_market_outlook("  ", _META, client=client)
    assert out["validation_failed"] is True and client.calls == []


def test_summarize_invalid_falls_back():
    client = _FakeClient(["not json", "still bad"])
    out = summarize_market_outlook("원문", _META, client=client)
    assert out["validation_failed"] is True and len(client.calls) == 2


# ── store ──
def test_store_upsert_idempotent(tmp_path):
    s = MarketOutlookStore(tmp_path / "m.json")
    assert s.upsert({"report_id": "36722", "broker": "KB증권", "date": "26.07.10"}) is True
    assert s.upsert({"report_id": "36722", "broker": "KB증권", "date": "26.07.10"}) is False
    assert len(s.list_reports()) == 1


def test_store_list_sorted_desc(tmp_path):
    s = MarketOutlookStore(tmp_path / "m.json")
    s.upsert({"report_id": "1", "date": "26.07.08"})
    s.upsert({"report_id": "2", "date": "26.07.10"})
    assert [r["date"] for r in s.list_reports()] == ["26.07.10", "26.07.08"]


# ── 서비스 ──
def test_service_fetch_and_summarize(monkeypatch, tmp_path):
    metas = [{"nid": "36722", "broker": "KB증권", "title": "t", "date": "26.07.10",
              "pdf_url": "https://x/m.pdf", "stock_code": None}]
    monkeypatch.setattr(naver_research, "fetch_reports", lambda cat, limit: list(metas))
    monkeypatch.setattr(naver_research, "download_pdf", lambda url, **k: "/tmp/m.pdf")
    monkeypatch.setattr(ingest, "extract_text", lambda p: "시황 원문")
    monkeypatch.setattr(
        mo, "summarize_market_outlook",
        lambda text, meta, client=None: {"summary": {"증권사": meta["broker"]}, "validation_failed": False},
    )
    store = MarketOutlookStore(tmp_path / "m.json")
    out = svc.fetch_and_summarize(limit=10, store=store)
    assert out == {"fetched": 1, "new": 1, "skipped": 0, "failed": 0}
    assert len(store.list_reports()) == 1


def test_service_fetch_uses_market_category(monkeypatch, tmp_path):
    seen = {}

    def _fake(cat, limit):
        seen["cat"] = cat
        return []

    monkeypatch.setattr(naver_research, "fetch_reports", _fake)
    svc.fetch_and_summarize(limit=5, store=MarketOutlookStore(tmp_path / "m.json"))
    assert seen["cat"] == "market"
