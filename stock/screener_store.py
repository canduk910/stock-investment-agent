"""전체 유니버스 스크리너 스캔 결과 저장소(SQL 공동 DB).

`report_repo.ScopedReportRepo` 패턴 — **메서드마다 새 짧은 세션**(배치 스캔이 병렬이어도 스레드
안전). session_factory 미주입 시 앱 기본(get_sessionmaker). 테스트는 인메모리 sessionmaker 주입.

계약:
- `upsert_scan(as_of_date, rows)` — 그 날짜 기존 행을 지우고 rows 를 저장(같은 날 재스캔=갱신).
- `latest_as_of()` — 가장 최근 스캔일("YYYY-MM-DD") | None.
- `list_results(as_of_date=None, market=None, stage=None)` — 최근 스캔 기본·market/stage 필터 옵션.

**현재가/등락률은 저장·반환하지 않는다**(무캐시 원칙1) — stage/band 등 확정 파생값만.
"""
from __future__ import annotations

from sqlalchemy import delete, func, select

from infra.db import get_sessionmaker
from infra.timeutil import utcnow as _utcnow
from stock.screener_models import ScreenerResultRow


def _spark_to_str(spark) -> str | None:
    """종가 리스트 → "c1,c2,..."(저장용). 빈/비수치 → None."""
    if not spark:
        return None
    parts = []
    for x in spark:
        try:
            parts.append(f"{float(x):.2f}")
        except (TypeError, ValueError):
            continue
    return ",".join(parts) or None


def _spark_from_str(text: str | None) -> list[float] | None:
    """저장 "c1,c2,..." → 종가 리스트(서빙용). 없으면 None."""
    if not text:
        return None
    out = []
    for tok in str(text).split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            out.append(float(tok))
        except ValueError:
            continue
    return out or None


def _entry_from_row(row: ScreenerResultRow) -> dict:
    """Row → 서빙/후보 dict. 계약 SSOT.

    ★현재가·현재 PER 은 여기 없다(무캐시 원칙1) — 서빙이 표시 top-N 만 라이브 조회해 얹는다.
    market_cap(정렬키·스캔일 스냅샷)·재무 3축 원천(roe/net_income_growth/debt_ratio)·avg_per
    (밸류 축용)·spark(미니차트)는 스캔 확정/파생 스냅샷이라 저장·반환한다.
    """
    return {
        "ticker": row.ticker,
        "name": row.name,
        "market": row.market,
        "stage": row.stage,
        "stage_name": row.stage_name,
        "arrangement": row.arrangement,
        "band_width_pct": row.band_width_pct,
        "band_direction": row.band_direction,
        "bars_in_stage": row.bars_in_stage,
        "market_cap": row.market_cap,
        "roe": row.roe,
        "net_income_growth": row.net_income_growth,
        "debt_ratio": row.debt_ratio,
        "avg_per": row.avg_per,
        "spark": _spark_from_str(row.spark),
    }


class ScreenerResultStore:
    """스캔 결과 공동 저장소(SQL 백엔드). db 미주입 시 메서드마다 새 세션(스레드 안전)."""

    def __init__(self, session_factory=None) -> None:
        self._sf = session_factory

    def _run(self, fn):
        """fn(db) 를 새 짧은 세션으로 실행하고 반드시 닫는다(스레드마다 자기 세션)."""
        factory = self._sf or get_sessionmaker()
        db = factory()
        try:
            return fn(db)
        finally:
            db.close()

    def upsert_scan(self, as_of_date: str, rows: list[dict]) -> int:
        """그 날짜의 기존 행을 모두 지우고 rows 저장(원자적 갱신). 저장 건수 반환.

        같은 as_of_date 재스캔 = 유니크(as_of_date,ticker) 충돌 없이 전량 교체(idempotent).
        """
        def _op(db):
            db.execute(delete(ScreenerResultRow).where(ScreenerResultRow.as_of_date == as_of_date))
            now = _utcnow()
            for r in rows or []:
                db.add(
                    ScreenerResultRow(
                        as_of_date=as_of_date,
                        ticker=r.get("ticker"),
                        name=r.get("name"),
                        market=r.get("market"),
                        stage=r.get("stage"),
                        stage_name=r.get("stage_name"),
                        arrangement=r.get("arrangement"),
                        band_width_pct=r.get("band_width_pct"),
                        band_direction=r.get("band_direction"),
                        bars_in_stage=r.get("bars_in_stage"),
                        market_cap=r.get("market_cap"),
                        roe=r.get("roe"),
                        net_income_growth=r.get("net_income_growth"),
                        debt_ratio=r.get("debt_ratio"),
                        avg_per=r.get("avg_per"),
                        spark=_spark_to_str(r.get("spark")),
                        scanned_at=now,
                    )
                )
            db.commit()
            return len(rows or [])

        return self._run(_op)

    def latest_as_of(self) -> str | None:
        """가장 최근 스캔일("YYYY-MM-DD") 또는 None(스캔 이력 없음)."""
        return self._run(lambda db: db.scalar(select(func.max(ScreenerResultRow.as_of_date))))

    def list_results(
        self, as_of_date: str | None = None, market: str | None = None, stage: int | None = None
    ) -> list[dict]:
        """스캔 결과 조회. as_of_date 미지정이면 최신 스캔일. market/stage 필터 옵션.

        stage=None 인 행(봉<40·조회실패)도 반환한다 — 후보(stage!=None) 필터링은 서빙이 결정.
        """
        def _op(db):
            target = as_of_date or db.scalar(select(func.max(ScreenerResultRow.as_of_date)))
            if target is None:
                return []
            q = select(ScreenerResultRow).where(ScreenerResultRow.as_of_date == target)
            if market is not None:
                q = q.where(ScreenerResultRow.market == market)
            if stage is not None:
                q = q.where(ScreenerResultRow.stage == stage)
            q = q.order_by(ScreenerResultRow.id)  # 저장(스캔) 순 안정 정렬
            return [_entry_from_row(r) for r in db.scalars(q).all()]

        return self._run(_op)


_default: ScreenerResultStore | None = None


def default_store() -> ScreenerResultStore:
    """앱 기본 세션팩토리 스토어(싱글턴). 배치/서빙 공용."""
    global _default
    if _default is None:
        _default = ScreenerResultStore()
    return _default
