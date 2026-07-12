"""리포트 라우트 테스트 — plan §"api/report.py" (P2, 라이브 미호출 mock).

api/main.py 는 편집 금지(라우터 wiring 은 리더 전담)라 로컬 FastAPI 앱으로 테스트한다:
  app = FastAPI(); app.include_router(api.report.router); TestClient(app).

경계(KIS 클라이언트·judgement·bundle·generate·store)를 monkeypatch 해 실 API/OpenAI 없이
계약을 검증한다:
- POST 생성: generate 결과를 반환 + 검증 통과 시 store.append 호출(저장) + regime_at_creation.
- POST 폴백: validation_failed=True 여도 200 + report=None + 정량요약. 폴백은 저장하지 않음.
- GET history: store.list_history 결과 반환(과거 평가 비교 데모).
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.report as report_mod


@pytest.fixture
def client(monkeypatch):
    # 경계 monkeypatch: KIS 클라이언트·judgement·bundle 조립은 mock(라이브 미호출).
    monkeypatch.setattr(report_mod, "_resolve_client", lambda *a, **k: object())
    monkeypatch.setattr(
        report_mod, "_build_judgement", lambda: {"regime": "확장", "recommended_cash_ratio": 60}
    )
    monkeypatch.setattr(
        report_mod,
        "collect_stock_bundle",
        lambda ticker, kis_client, judgement: {
            "ticker": ticker,
            "basic": {"name": "삼성전자"},
            "summary": {"current_per": 12.0, "valuation_label": "적정"},
            "regime_gate": {"regime": "확장", "single_cap": 3},
            "partial_failure": [],
        },
    )
    app = FastAPI()
    app.include_router(report_mod.router)
    return TestClient(app)


_VALID = {
    "종합의견": "중립",
    "요약": "요약",
    "투자포인트": ["a"],
    "리스크요인": ["b"],
    "국면정합성": "정합성",
    "면책고지": "참고용",
}


def _stub_generate(result):
    def _gen(bundle, judgement, *, client=None):
        return result

    return _gen


class _SpyStore:
    def __init__(self):
        self.appended = []
        self._history = {}

    def append(self, ticker, report_json, *, regime_at_creation, created_at=None):
        entry = {
            "created_at": created_at or "2026-07-09T00:00:00+00:00",
            "regime_at_creation": regime_at_creation,
            "report_json": report_json,
        }
        self.appended.append((ticker, entry))
        self._history.setdefault(ticker, []).append(entry)
        return entry

    def list_history(self, ticker):
        # 실 store 계약과 동일하게 created_at 내림차순(최신 우선) — 중복 게이트가 최신을 [0]으로 본다.
        return sorted(
            self._history.get(ticker, []), key=lambda e: e.get("created_at", ""), reverse=True
        )


# ── POST 생성(검증 통과) ─────────────────────────────────────────────────────


def test_post_report_generates_and_stores(client, monkeypatch):
    store = _SpyStore()
    monkeypatch.setattr(report_mod, "_STORE", store)
    monkeypatch.setattr(
        report_mod,
        "generate_stock_report",
        _stub_generate(
            {"report": _VALID, "validation_failed": False, "quant_summary": {"current_per": 12.0}}
        ),
    )

    r = client.post("/api/detail/005930/report")
    assert r.status_code == 200
    body = r.json()
    assert body["validation_failed"] is False
    assert body["report"]["종합의견"] == "중립"
    assert body["ticker"] == "005930"
    # 검증 통과분만 저장(regime_at_creation = 생성 시점 국면).
    assert len(store.appended) == 1
    assert store.appended[0][0] == "005930"
    assert store.appended[0][1]["regime_at_creation"] == "확장"


def test_post_report_returns_created_at(client, monkeypatch):
    store = _SpyStore()
    monkeypatch.setattr(report_mod, "_STORE", store)
    monkeypatch.setattr(
        report_mod,
        "generate_stock_report",
        _stub_generate({"report": _VALID, "validation_failed": False, "quant_summary": {}}),
    )
    body = client.post("/api/detail/005930/report").json()
    assert body["created_at"]  # 저장 시각 반환(히스토리 정렬 키)


# ── POST 폴백(검증 실패) ─────────────────────────────────────────────────────


def test_post_report_fallback_not_stored(client, monkeypatch):
    store = _SpyStore()
    monkeypatch.setattr(report_mod, "_STORE", store)
    monkeypatch.setattr(
        report_mod,
        "generate_stock_report",
        _stub_generate(
            {
                "report": None,
                "validation_failed": True,
                "message": "AI 서술 생성 실패",
                "quant_summary": {"current_per": 12.0},
            }
        ),
    )

    r = client.post("/api/detail/005930/report")
    assert r.status_code == 200  # 폴백도 200(부분실패 보존)
    body = r.json()
    assert body["validation_failed"] is True
    assert body["report"] is None
    assert body["quant_summary"] == {"current_per": 12.0}  # 정량요약은 남는다
    assert store.appended == []  # 폴백은 저장하지 않음


# ── 중복 저장 게이트(IMP-16) ─────────────────────────────────────────────────


def test_post_report_dedup_same_opinion_and_regime(client, monkeypatch):
    # 같은 종합의견·국면으로 두 번 생성 → 두 번째는 히스토리 중복 저장하지 않는다(반복 클릭 노이즈 방지).
    store = _SpyStore()
    monkeypatch.setattr(report_mod, "_STORE", store)
    monkeypatch.setattr(
        report_mod,
        "generate_stock_report",
        _stub_generate({"report": _VALID, "validation_failed": False, "quant_summary": {}}),
    )
    r1 = client.post("/api/detail/005930/report")
    r2 = client.post("/api/detail/005930/report")
    assert r1.status_code == 200 and r2.status_code == 200
    assert len(store.appended) == 1  # 두 번째(동일 평가)는 저장 생략
    assert r2.json()["report"]["종합의견"] == "중립"  # 리포트 자체는 두 번 다 반환


def test_post_report_stores_when_opinion_changes(client, monkeypatch):
    # 종합의견이 바뀌면(재평가) 저장한다 — dedup 은 '직전과 동일'일 때만.
    store = _SpyStore()
    monkeypatch.setattr(report_mod, "_STORE", store)
    seq = iter([
        {"report": {**_VALID, "종합의견": "중립"}, "validation_failed": False, "quant_summary": {}},
        {"report": {**_VALID, "종합의견": "신중"}, "validation_failed": False, "quant_summary": {}},
    ])
    monkeypatch.setattr(report_mod, "generate_stock_report", lambda b, j, *, client=None: next(seq))
    client.post("/api/detail/005930/report")
    client.post("/api/detail/005930/report")
    assert len(store.appended) == 2


# ── judgement 실패(국면 수집 실패) ───────────────────────────────────────────


def test_post_report_survives_judgement_failure(client, monkeypatch):
    # 국면 수집이 실패해도 리포트 생성은 진행(judgement=None → regime_at_creation=None).
    def boom():
        raise RuntimeError("fred down")

    monkeypatch.setattr(report_mod, "_build_judgement", boom)
    store = _SpyStore()
    monkeypatch.setattr(report_mod, "_STORE", store)
    monkeypatch.setattr(
        report_mod,
        "generate_stock_report",
        _stub_generate({"report": _VALID, "validation_failed": False, "quant_summary": {}}),
    )

    r = client.post("/api/detail/005930/report")
    assert r.status_code == 200
    assert store.appended[0][1]["regime_at_creation"] is None


# ── GET history ──────────────────────────────────────────────────────────────


def test_get_history_returns_stored(client, monkeypatch):
    store = _SpyStore()
    store.append("005930", _VALID, regime_at_creation="과열", created_at="2026-01-01T00:00:00+00:00")
    monkeypatch.setattr(report_mod, "_STORE", store)

    r = client.get("/api/detail/005930/report/history")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "005930"
    assert len(body["history"]) == 1
    assert body["history"][0]["regime_at_creation"] == "과열"


def test_get_history_empty(client, monkeypatch):
    monkeypatch.setattr(report_mod, "_STORE", _SpyStore())
    body = client.get("/api/detail/999999/report/history").json()
    assert body["history"] == []


# ── ticker 검증(IMP-02) — 불량 ticker 가 외부호출·저장을 트리거하지 않게 ────────

def test_post_report_rejects_invalid_ticker(client, monkeypatch):
    # 불량 ticker 는 400 — collect_stock_bundle(KIS)·generate(OpenAI)·store.append 를 트리거하지 않는다.
    def _boom_gen(*a, **k):
        raise AssertionError("불량 ticker 인데 generate 가 호출됐다(검증 미차단)")

    monkeypatch.setattr(report_mod, "generate_stock_report", _boom_gen)
    store = _SpyStore()
    monkeypatch.setattr(report_mod, "_STORE", store)
    for bad in ("12345", "1234567", "abc_de"):
        r = client.post(f"/api/detail/{bad}/report")
        assert r.status_code == 400, f"{bad}: {r.status_code}"
    assert store.appended == []  # 오염 저장 0


def test_get_history_rejects_invalid_ticker(client, monkeypatch):
    monkeypatch.setattr(report_mod, "_STORE", _SpyStore())
    r = client.get("/api/detail/abc_de/report/history")
    assert r.status_code == 400
