"""현재 화면 스냅샷 빌더 — kind별 포맷·top-N·기준시각·graceful·비데이터 None(서비스 boundary mock).

KIS 해석은 `vc._resolve`(본인/공유/env → ResolvedKis) 단일 경계로 mock — 실 KIS/DB 미호출.
"""
from __future__ import annotations

import chat.view_context as vc


def _stub_resolve(monkeypatch, *, cano="C", prdt="01"):
    """vc._resolve 를 stub ResolvedKis(빈 클라이언트 + 고정 계좌)로 교체."""
    from api.detail import ResolvedKis

    monkeypatch.setattr(vc, "_resolve", lambda user, db: ResolvedKis(object(), cano, prdt, "shared"))


def _no_kis(monkeypatch):
    _stub_resolve(monkeypatch)
    monkeypatch.setattr(vc, "_safe_judgement", lambda: None)


# ── balance ──
def test_balance_context(monkeypatch):
    _no_kis(monkeypatch)
    monkeypatch.setattr(
        "collectors.kis.balance.inquire_balance",
        lambda c, cano, prdt: {
            "holdings": [
                {"ticker": "005930", "name": "삼성전자", "qty": 10,
                 "eval_amount": 800000, "pnl_amount": 100000, "pnl_pct": 14.28},
            ],
            "summary": {"net_asset": 1900000, "deposit": 500000,
                        "total_eval": 1400000, "pnl_amount": 50000},
        },
    )
    out = vc.build_view_context("balance", {})
    assert out is not None
    assert out.startswith("기준시각:")
    assert "순자산" in out and "삼성전자" in out and "005930" in out


def test_balance_top_n_and_truncation(monkeypatch):
    _no_kis(monkeypatch)
    holdings = [
        {"ticker": f"{i:06d}", "name": f"종목{i}", "qty": i + 1,
         "eval_amount": (i + 1) * 1000, "pnl_amount": i, "pnl_pct": 1.0}
        for i in range(20)
    ]
    monkeypatch.setattr(
        "collectors.kis.balance.inquire_balance",
        lambda c, cano, prdt: {"holdings": holdings, "summary": {"net_asset": 1}},
    )
    out = vc.build_view_context("balance", {})
    assert "…외 12종목" in out  # top-8 만 표시 + 나머지 요약
    assert len(out) <= 1600  # 전체 길이 상한(안전망)


def test_balance_kis_fail_graceful(monkeypatch):
    def _boom(user, db):  # 자격증명 해석/조회 실패 시뮬
        raise Exception("kis down")

    monkeypatch.setattr(vc, "_resolve", _boom)
    out = vc.build_view_context("balance", {})
    assert out is not None and "조회 불가" in out  # 크래시 아님, 안내 노트


# ── watchlist ──
def test_watchlist_context(monkeypatch):
    _no_kis(monkeypatch)
    monkeypatch.setattr(
        "watchlist.service.build_watchlist_view",
        lambda store, uid, client, judgement: {
            "items": [
                {"ticker": "005930", "stock_name": "삼성전자", "current_price": 78000,
                 "change_rate": 1.2, "per": 12.0, "target_price": 90000,
                 "target_status": "far", "sell_target_price": 110000,
                 "sell_target_status": "far"},
            ],
            "regime": {"regime": "확장"},  # 국면명만(진입게이트 폐기 — 항목3)
            "partial_failure": [],
        },
    )
    out = vc.build_view_context("watchlist", {})
    assert "관심종목" in out and "삼성전자" in out
    # 매수·매도 목표가를 모두 인용(분리 저장).
    assert "국면 확장" in out and "매수목표" in out and "매도목표" in out


def test_watchlist_empty_note(monkeypatch):
    _no_kis(monkeypatch)
    monkeypatch.setattr(
        "watchlist.service.build_watchlist_view",
        lambda *a, **k: {"items": [], "regime": None, "partial_failure": []},
    )
    out = vc.build_view_context("watchlist", {})
    assert "비어 있음" in out


# ── stock_report ──
def test_stock_context(monkeypatch):
    _stub_resolve(monkeypatch)
    monkeypatch.setattr(
        vc, "_safe_judgement",
        lambda: {"regime": "확장", "params": {"cash": 60}},  # 현금비중만(항목3)
    )
    monkeypatch.setattr(
        "collectors.kis.inquire_price.inquire_price",
        lambda c, t: {"ticker": "005930", "price": 78000, "change_rate": 1.2,
                      "per": 12.0, "pbr": 1.3, "week52_high": 90000, "week52_low": 60000},
    )

    class _Store:
        def list_reports(self, t):
            return [{"summary": {"증권사": "한화투자증권", "투자의견": "매수",
                                 "목표주가": "9만원", "요약": "실적 개선 기대"}}]

    monkeypatch.setattr("chat.analyst_store.default_store", lambda: _Store())
    monkeypatch.setattr(vc, "_latest_ai_report", lambda t: None)  # 실 report_store 읽기 차단(hermetic)
    out = vc.build_view_context("stock_report", {"ticker": "005930", "stock_name": "삼성전자"})
    assert out is not None
    # 52주 고/저 원값 + 위치 — 에이전트 목표가 추천 근거(범위 앵커). 원값을 직접 핀(죽은 단정 방지).
    assert "삼성전자" in out and "현재가" in out and "PER" in out
    assert "52주 고" in out and "90,000" in out and "60,000" in out  # fixture high/low 원값 노출
    # 애널리스트 의견은 출처 귀속(판정 아님).
    assert "한화투자증권" in out and "리포트가 밝힌 의견" in out
    # 저장된 AI 리포트가 없으면(None) AI 리포트 블록 미포함(기존 동작).
    assert "AI 종합리포트" not in out


def test_stock_bad_ticker_none():
    assert vc.build_view_context("stock_report", {"ticker": "bad"}) is None
    assert vc.build_view_context("stock_report", {}) is None


def _stock_common(monkeypatch, *, analyst=None):
    """_stock_context 공통 스텁 — KIS 해석·시세·애널리스트(기본 없음). AI 리포트는 테스트별 주입."""
    _stub_resolve(monkeypatch)
    monkeypatch.setattr(
        "collectors.kis.inquire_price.inquire_price",
        lambda c, t: {"ticker": "005930", "price": 78000, "change_rate": 1.2,
                      "per": 12.0, "pbr": 1.3, "week52_high": 90000, "week52_low": 60000},
    )

    class _Store:
        def list_reports(self, t):
            return list(analyst or [])

    monkeypatch.setattr("chat.analyst_store.default_store", lambda: _Store())


def test_stock_context_includes_stored_ai_report(monkeypatch):
    # 사용자가 종목 상세에서 생성해 둔 AI 리포트가 그 종목 문의 시 컨텍스트에 실린다.
    _stock_common(monkeypatch)
    entry = {
        "created_at": "2026-07-24T01:00:00+00:00",
        "regime_at_creation": "확장",
        "report_json": {
            "종합의견": "중립",
            "요약": "메모리 업황 회복 기대와 밸류에이션 부담이 병존.",
            "투자포인트": ["HBM 수요 확대", "원가 개선"],
            "리스크요인": ["업황 둔화", "환율 변동"],
            "국면정합성": "확장 국면 권장 현금비중 대비 무난한 편.",
            "면책고지": "투자 판단 책임은 본인.",
        },
    }
    monkeypatch.setattr(vc, "_latest_ai_report", lambda t: entry)
    out = vc.build_view_context("stock_report", {"ticker": "005930", "stock_name": "삼성전자"})
    assert out is not None
    assert "AI 종합리포트" in out and "매수·매도 판정 아님" in out  # 출처·안전 문구
    assert "종합의견 중립" in out and "2026-07-24" in out  # 의견 + 생성일
    assert "HBM 수요 확대" in out and "업황 둔화" in out  # 투자포인트·리스크
    assert "국면정합성" in out
    assert len(out) <= vc._MAX_CHARS  # 예산 내


def test_stock_context_ai_report_partial_graceful(monkeypatch):
    # report_json 이 일부 키만 있어도 크래시 없이 있는 것만 렌더(폴백/구버전 방어).
    _stock_common(monkeypatch)
    monkeypatch.setattr(
        vc, "_latest_ai_report",
        lambda t: {"created_at": "2026-07-24T00:00:00+00:00", "report_json": {"종합의견": "긍정적"}},
    )
    out = vc.build_view_context("stock_report", {"ticker": "005930", "stock_name": "삼성전자"})
    assert out is not None and "종합의견 긍정적" in out


def test_stock_context_no_ai_report_when_store_empty(monkeypatch):
    # 미생성(None) → AI 리포트 블록 없음(그대로 기존 스냅샷).
    _stock_common(monkeypatch)
    monkeypatch.setattr(vc, "_latest_ai_report", lambda t: None)
    out = vc.build_view_context("stock_report", {"ticker": "005930", "stock_name": "삼성전자"})
    assert out is not None and "AI 종합리포트" not in out


def test_stock_kis_fail_graceful(monkeypatch):
    _stub_resolve(monkeypatch)
    monkeypatch.setattr(vc, "_safe_judgement", lambda: None)

    def _boom(c, t):
        raise Exception("kis down")

    monkeypatch.setattr("collectors.kis.inquire_price.inquire_price", _boom)
    monkeypatch.setattr("chat.analyst_store.default_store",
                        lambda: type("S", (), {"list_reports": lambda self, t: []})())
    out = vc.build_view_context("stock_report", {"ticker": "005930"})
    assert out is not None and "조회 불가" in out  # 시세 실패해도 노트(크래시 아님)


# ── 비데이터 kind / 방어 ──
def test_non_data_kinds_none():
    assert vc.build_view_context("macro_dashboard", {}) is None
    assert vc.build_view_context("manage_watchlist", {}) is None
    assert vc.build_view_context("unknown", {}) is None


def test_data_bearing_kinds_ssot():
    assert vc.DATA_BEARING_KINDS == frozenset({"balance", "watchlist", "stock_report"})
