"""전체 유니버스 스크리너 스캔 결과 ORM 모델 — **공동 관리(전역 공유, user 무관)**.

배치 스캐너(`stock/screener_scan.py`)가 매일(장마감 후) 한국시장 보통주를 대순환 단계로
스캔해 여기에 저장하고, 서빙(`api/screener.py` scope=cached)이 최신 스캔일 결과를 읽는다.

**저장 대상 = 확정 파생값만**(대순환 stage/band 는 확정 과거 40봉 기반이라 캐시·저장 가능 —
시황 궤적 `macro:history:` 선례). **현재가·등락률은 저장하지 않는다**(무캐시 원칙1 — 클릭 시
종목 상세가 라이브 조회). (as_of_date, ticker) 유니크 = 같은 날 재스캔 시 idempotent 갱신.
로컬 SQLite / 프로덕션 GCP Cloud SQL Postgres(JSON 미사용) 무변경.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from infra.db import Base
# UTC now SSOT(infra/timeutil) — Column default 콜러블(호출 시점 평가).
from infra.timeutil import utcnow as _utcnow


class ScreenerResultRow(Base):
    __tablename__ = "screener_results"
    __table_args__ = (
        UniqueConstraint("as_of_date", "ticker", name="uq_screener_date_ticker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    as_of_date: Mapped[str] = mapped_column(String(10), index=True, nullable=False)  # 스캔일 KST "YYYY-MM-DD"
    ticker: Mapped[str] = mapped_column(String(6), nullable=False)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    market: Mapped[str | None] = mapped_column(String(16), nullable=True)  # KOSPI | KOSDAQ
    # 대순환 확정 파생값(판정=코드). stage None = 봉<40·조회실패(판정 보류).
    stage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stage_name: Mapped[str | None] = mapped_column(String(32), nullable=True)
    arrangement: Mapped[str | None] = mapped_column(String(32), nullable=True)
    band_width_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    band_direction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    bars_in_stage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scanned_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
