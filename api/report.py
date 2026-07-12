"""구조화 리포트 생성·히스토리 라우트 — plan §"api/report.py" (P2).

두 엔드포인트:
- POST /api/detail/{ticker}/report — 번들 조회 → 국면 판정 → generate_stock_report(생성·검증)
  → 검증 통과분만 히스토리에 저장 → 반환. 폴백(validation_failed)도 200(정량요약 보존).
- GET  /api/detail/{ticker}/report/history — 과거 평가 히스토리(과거 대비 비교 데모).

api/detail.py 의 자산을 재사용한다(_build_kis_client·_build_judgement·collect_stock_bundle
— 순수 조회·순수 엔진, 사이클 없음). LLM 생성은 chat.report(설명만, 판정은 코드).

⚠ api/main.py 는 리더가 include 한다. 여기서는 router 만 정의하고 main.py 를 편집하지 않는다.
테스트는 로컬 FastAPI 앱에 이 router 를 include 해 계약을 검증한다(라이브 미호출 mock).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

# api.detail 재사용(순수 조회·엔진 조립 — 사이클 없음). 모듈 네임스페이스에 바인딩해
# 테스트가 report_mod._build_judgement 등을 monkeypatch 할 수 있게 한다.
from api.deps import assert_valid_ticker
from api.detail import (
    _build_judgement,
    _resolve_client,
    collect_stock_bundle,
)
from auth.deps import get_current_user_optional
from auth.models import User
from chat.report import generate_stock_report
from chat.report_store import JsonFileReportStore
from infra.db import get_db

router = APIRouter()

# 히스토리 저장 싱글톤(로컬 스탠드인). 배포 시 DynamoDB stock_report 테이블로 교체.
_STORE = JsonFileReportStore()


def _get_store():
    """store 접근 진입점 — watchlist.py 와 동일 규약(IMP-12). 라우트는 항상 이 함수 경유."""
    return _STORE


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _same_as_latest(store, ticker: str, opinion, regime) -> bool:
    """직전 저장과 종합의견·국면이 모두 같으면 중복(반복 클릭 노이즈) → 저장 생략(IMP-16).

    주의: 리포트 자체는 사용자에게 항상 반환된다 — 비교 히스토리 저장만 생략한다(데모 품질 우선).
    같은 종합의견·국면이면 정당한 재평가도 걸러질 수 있다(허용 가능한 트레이드오프).
    """
    history = store.list_history(ticker)  # 최신 우선(내림차순)
    if not history:
        return False
    latest = history[0]
    return (
        (latest.get("report_json") or {}).get("종합의견") == opinion
        and latest.get("regime_at_creation") == regime
    )


@router.post("/api/detail/{ticker}/report")
def create_report(
    ticker: str,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> dict:
    """리포트 생성·검증·저장·반환(§6.5b). 국면 수집 실패는 regime_at_creation=None(항상 200).

    공개 유지(옵션 인증) — 로그인+등록 시 본인 KIS 키, 아니면 공유 fallback.
    """
    assert_valid_ticker(ticker)  # 불량 코드가 KIS·OpenAI·저장을 트리거하기 전에 400(IMP-02)
    try:
        judgement = _build_judgement()
    except Exception:
        judgement = None  # 국면 수집 실패해도 리포트 생성은 진행(regime_at_creation=None)

    client = _resolve_client(user, db)
    bundle = collect_stock_bundle(ticker, client, judgement)

    result = generate_stock_report(bundle, judgement or {}, client=None)

    regime_at_creation = judgement.get("regime") if judgement else None
    created_at = _now_iso()

    # 검증 통과분만 히스토리에 저장(폴백 미저장). 직전과 동일 평가(종합의견·국면)면 중복 저장 생략(IMP-16).
    report = result.get("report")
    if not result.get("validation_failed") and report is not None:
        store = _get_store()
        if not _same_as_latest(store, ticker, report.get("종합의견"), regime_at_creation):
            store.append(
                ticker,
                report,
                regime_at_creation=regime_at_creation,
                created_at=created_at,
            )

    return {
        "ticker": ticker,
        "report": result.get("report"),
        "validation_failed": result.get("validation_failed", False),
        "quant_summary": result.get("quant_summary"),
        "message": result.get("message"),
        "regime_at_creation": regime_at_creation,
        "created_at": created_at,
    }


@router.get("/api/detail/{ticker}/report/history")
def report_history(ticker: str) -> dict:
    """과거 평가 히스토리(created_at 내림차순 — 최신 우선). 과거 대비 비교 데모."""
    assert_valid_ticker(ticker)  # IMP-02
    return {"ticker": ticker, "history": _get_store().list_history(ticker)}
