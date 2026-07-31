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
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from chat.market_outlook import summarize_market_outlook
from chat.market_outlook_schema import MarketOutlookSummary
from chat.market_outlook_store import MarketOutlookStore
from infra.db import Base, import_models


def _sql_market_store():
    """SQL 공동 DB(인메모리) 백엔드의 시황 store(격리된 새 엔진)."""
    import_models()
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False)
    return MarketOutlookStore(session_factory=sf)

_META = {"broker": "KB증권", "title": "7/10 모닝코멘트", "date": "26.07.10"}
_VALID = {
    "증권사": "KB증권", "제목": "7/10 모닝코멘트", "시장전망": "중립",
    "요약": "수급 개선 기대.", "핵심요지": ["외국인 순매수", "실적 시즌 진입"],
    "리스크요인": ["환율 변동성"], "면책고지": "이 요약은 시황 리포트 내용이며 자문이 아니다.",
    "세줄요약": ["외국인 순매수 전환", "실적 시즌 기대", "환율은 변수"],
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


# ── 세줄요약(항목4: 3줄 압축 요약) ──
def test_schema_세줄요약_present():
    # 컴팩트 카드용 3줄요약 — list[str] 로 노출.
    s = MarketOutlookSummary(**_VALID)
    assert s.세줄요약 == ["외국인 순매수 전환", "실적 시즌 기대", "환율은 변수"]


def test_schema_rejects_empty_세줄요약():
    # 최소 1줄 강제(빈 3줄요약 방지).
    with pytest.raises(ValidationError):
        MarketOutlookSummary(**{**_VALID, "세줄요약": []})


def test_schema_세줄요약_max_3():
    # 3줄 상한 — 4개 이상은 거부(컴팩트 카드 과밀 방지).
    with pytest.raises(ValidationError):
        MarketOutlookSummary(**{**_VALID, "세줄요약": ["a", "b", "c", "d"]})


def test_prompt_instructs_세줄요약():
    # 요약 프롬프트가 세줄요약(3줄 압축)을 지시하고 JSON 키로 명시한다.
    prompt = mo._build_summary_prompt("시황 원문", _META)
    assert "세줄요약" in prompt
    assert "3줄" in prompt or "3개" in prompt


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
    s = _sql_market_store()
    assert s.upsert({"report_id": "36722", "broker": "KB증권", "date": "26.07.10"}) is True
    assert s.upsert({"report_id": "36722", "broker": "KB증권", "date": "26.07.10"}) is False
    assert len(s.list_reports()) == 1


def test_store_list_sorted_desc(tmp_path):
    s = _sql_market_store()
    s.upsert({"report_id": "1", "date": "26.07.08"})
    s.upsert({"report_id": "2", "date": "26.07.10"})
    assert [r["date"] for r in s.list_reports()] == ["26.07.10", "26.07.08"]


# ── build_recent_outlook_context (챗 프롬프트 주입용·추가 LLM 0) ──
class _StubStore:
    def __init__(self, reports):
        self._reports = reports

    def list_reports(self):
        return list(self._reports)


def _outlook_entry(broker, stance):
    return {
        "report_id": broker, "broker": broker, "title": f"{broker} 시황", "date": "26.07.20",
        "summary": {"증권사": broker, "제목": f"{broker} 시황", "시장전망": stance, "요약": "박스권.",
                    "핵심요지": ["금리"], "리스크요인": ["환율"], "면책고지": "자문 아님."},
    }


def test_build_recent_outlook_context_formats_recent_n():
    store = _StubStore([_outlook_entry(b, "중립") for b in ("KB", "삼성", "미래", "NH")])
    ctx = mo.build_recent_outlook_context(limit=3, store=store)
    assert ctx and "KB" in ctx and "삼성" in ctx and "미래" in ctx
    assert "NH" not in ctx  # limit=3 → 최근 3개만
    assert "시장전망" in ctx  # format_market_outlook_context 포맷 사용


def test_build_recent_outlook_context_caps_chars():
    ctx = mo.build_recent_outlook_context(
        limit=3, max_chars=200, store=_StubStore([_outlook_entry("KB", "중" * 5000)])
    )
    assert ctx is not None and len(ctx) <= 200


def test_build_recent_outlook_context_empty_is_none():
    assert mo.build_recent_outlook_context(store=_StubStore([])) is None


def test_build_recent_outlook_context_graceful_on_store_error():
    class _BoomStore:
        def list_reports(self):
            raise RuntimeError("db down")

    assert mo.build_recent_outlook_context(store=_BoomStore()) is None


# ── 시황 stale 판정 + 동기 최신화(ensure_fresh_outlook) — macro_view 턴 훅 ──
# 배경: intent=macro_view 챗 턴에서 저장 시황이 시스템일자(KST)보다 오래됐으면 그 턴에 동기 수집.
# 하루 1회 서버 가드·타임아웃 상한·전면 graceful(예외로 챗이 깨지지 않음).
def _dated_entry(date):
    e = _outlook_entry("KB", "중립")
    e["date"] = date
    return e


@pytest.fixture(autouse=True)
def _reset_outlook_guard():
    # 모듈 전역 하루 1회 가드를 테스트마다 리셋(테스트 간 오염 방지).
    mo._reset_outlook_attempt()
    yield
    mo._reset_outlook_attempt()


def test_today_stamp_kst_format():
    import re

    stamp = mo._today_stamp_kst()
    # 저장 date 포맷("YY.MM.DD", zero-padded)과 일치해야 문자열 비교로 stale 판정 가능.
    assert re.fullmatch(r"\d{2}\.\d{2}\.\d{2}", stamp)


def test_outlook_is_stale_true_when_latest_older():
    store = _StubStore([_dated_entry("26.07.19")])
    assert mo.outlook_is_stale("26.07.20", store=store) is True


def test_outlook_is_stale_false_when_latest_is_today():
    store = _StubStore([_dated_entry("26.07.20")])
    assert mo.outlook_is_stale("26.07.20", store=store) is False


def test_outlook_is_stale_true_when_empty():
    # 저장분 없음 → stale(수집 시도 대상).
    assert mo.outlook_is_stale("26.07.20", store=_StubStore([])) is True


def test_outlook_is_stale_false_on_store_error():
    # 조회 실패는 크래시 없이 False(수집 시도 안 함 — 안전한 no-op).
    class _BoomStore:
        def list_reports(self):
            raise RuntimeError("db down")

    assert mo.outlook_is_stale("26.07.20", store=_BoomStore()) is False


def test_ensure_fresh_outlook_fresh_is_noop(monkeypatch):
    # 오늘자 저장분 있음 → 수집 미호출·"fresh".
    called = {"n": 0}
    monkeypatch.setattr(svc, "fetch_and_summarize", lambda **k: called.__setitem__("n", called["n"] + 1) or {})
    status = mo.ensure_fresh_outlook(today_stamp="26.07.20", store=_StubStore([_dated_entry("26.07.20")]))
    assert status == "fresh" and called["n"] == 0


def test_ensure_fresh_outlook_collects_when_stale(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(svc, "fetch_and_summarize", lambda **k: called.__setitem__("n", called["n"] + 1) or {"new": 1})
    status = mo.ensure_fresh_outlook(today_stamp="26.07.20", store=_StubStore([_dated_entry("26.07.19")]))
    assert status == "collected" and called["n"] == 1


def test_ensure_fresh_outlook_daily_guard_skips_second(monkeypatch):
    # 같은 날 두 번째 호출은 재수집 안 함(하루 1회 가드) — 주말/공휴일 무자료 폭주 방지.
    called = {"n": 0}
    monkeypatch.setattr(svc, "fetch_and_summarize", lambda **k: called.__setitem__("n", called["n"] + 1) or {})
    store = _StubStore([_dated_entry("26.07.19")])
    first = mo.ensure_fresh_outlook(today_stamp="26.07.20", store=store)
    second = mo.ensure_fresh_outlook(today_stamp="26.07.20", store=store)
    assert first == "collected" and second == "skipped_guard"
    assert called["n"] == 1  # 수집 1회만


def test_ensure_fresh_outlook_timeout_is_graceful(monkeypatch):
    # 수집이 타임아웃을 넘기면 "attempted"(백그라운드 계속·그 턴은 기존 저장분 사용). 예외 없음.
    import time

    def _slow(**k):
        time.sleep(0.3)
        return {}

    monkeypatch.setattr(svc, "fetch_and_summarize", _slow)
    status = mo.ensure_fresh_outlook(today_stamp="26.07.20", store=_StubStore([_dated_entry("26.07.19")]), timeout=0.01)
    assert status == "attempted"


def test_ensure_fresh_outlook_error_is_graceful(monkeypatch):
    # 수집 중 예외는 "error"(no raise) — 챗 흐름이 시황 수집으로 깨지지 않음.
    def _boom(**k):
        raise RuntimeError("naver down")

    monkeypatch.setattr(svc, "fetch_and_summarize", _boom)
    status = mo.ensure_fresh_outlook(today_stamp="26.07.20", store=_StubStore([_dated_entry("26.07.19")]))
    assert status == "error"


def test_ensure_fresh_outlook_never_raises(monkeypatch):
    # stale 판정 단계부터 예외여도 "error" — 절대 예외를 밖으로 내지 않는다.
    def _boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(mo, "outlook_is_stale", _boom)
    assert mo.ensure_fresh_outlook(today_stamp="26.07.20") == "error"


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
    store = _sql_market_store()
    out = svc.fetch_and_summarize(limit=10, store=store)
    assert out == {"fetched": 1, "new": 1, "skipped": 0, "failed": 0}
    assert len(store.list_reports()) == 1


def test_service_fetch_uses_market_category(monkeypatch, tmp_path):
    seen = {}

    def _fake(cat, limit):
        seen["cat"] = cat
        return []

    monkeypatch.setattr(naver_research, "fetch_reports", _fake)
    svc.fetch_and_summarize(limit=5, store=_sql_market_store())
    assert seen["cat"] == "market"
