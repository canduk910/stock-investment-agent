"""사이트 통계 API — 가입자수 + 방문자수(헤드라인 표시). 공개·개인정보 없음·항상 200 graceful.

- `POST /api/visit` : 방문 1건 기록(앱 로드 시 프론트가 1회 호출). 인증 불요(전 방문자 집계).
- `GET  /api/stats` : 가입자수(회원 총수) + 방문(누적·오늘). 톱바 헤드라인이 표시.

집계 수치만 반환한다(이메일 등 PII 없음). DB 오류에도 UI 를 깨지 않도록 0 폴백.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from infra import site_stats
from infra.db import get_db

router = APIRouter()


@router.post("/api/visit")
def record_visit(db: Session = Depends(get_db)) -> dict:
    try:
        return site_stats.record_visit(db)
    except Exception:  # 집계 실패가 앱 로드를 막지 않도록 graceful
        return {"total_visits": 0, "today_visits": 0}


@router.get("/api/stats")
def site_stats_route(db: Session = Depends(get_db)) -> dict:
    try:
        return site_stats.get_site_stats(db)
    except Exception:
        return {"member_count": 0, "total_visits": 0, "today_visits": 0}
