"""전체 유니버스 대순환 배치 스캐너 — 보통주 전종목 스캔 → DB 저장(조회 전용·판정=코드).

파이프라인: 보통주 유니버스(`stock.universe.common_stocks(load_stock_master())`) → 종목별 일봉
1콜(`stock.screener._fetch_cycle`, 90일창≈60봉) 병렬 → `grand_cycle_for_chart` 로 현재 단계 →
`ScreenerResultStore.upsert_scan(as_of_date, rows)` 저장. **사용자 대면 아님(배치)이라 느려도 됨** —
동시성 상한(레이트리밋 보호) + per-item graceful(한 종목 실패가 전체 안 죽임).

실행: 로컬 `uv run python -m stock.screener_scan` / Cloud Run Job(같은 이미지·300s 제약 없음).
안전: 매매 API 0(랭킹·일봉 조회만)·단계 판정=순수코드(LLM/랜덤 0)·**일봉 무캐시**(stage 확정
파생값만 DB 저장)·시크릿 노출 0.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from collectors.stock_master import load_stock_master
from infra.timeutil import KST
from stock.screener import _fetch_cycle  # 종목 1개 일봉→대순환 판정(90일창·단일 콜) 재사용
from stock.universe import common_stocks

logger = logging.getLogger(__name__)

DEFAULT_CONCURRENCY = 8  # KIS 유량 보호 상한(배치는 느려도 됨). EGW00201 backoff 는 client 가 처리.


def _today_kst() -> str:
    """스캔일(KST) "YYYY-MM-DD" — 한국 장마감 기준 날짜 경계."""
    return datetime.now(KST).strftime("%Y-%m-%d")


def _row_from(stock: dict, cycle: dict | None) -> dict:
    """유니버스 종목 + 대순환 판정 → 저장 행(현재가·등락률 없음, 무캐시 원칙1)."""
    gc = cycle or {}  # None: 봉<40·조회실패 → stage 판정 보류
    return {
        "ticker": stock.get("ticker"),
        "name": stock.get("name"),
        "market": stock.get("market"),
        "stage": gc.get("stage"),
        "stage_name": gc.get("stage_name"),
        "arrangement": gc.get("arrangement"),
        "band_width_pct": gc.get("band_width_pct"),
        "band_direction": gc.get("band_direction"),
        "bars_in_stage": gc.get("bars_in_stage"),
    }


def scan_all(client, store, *, universe=None, on_progress=None,
             concurrency=DEFAULT_CONCURRENCY, as_of_date=None) -> dict:
    """보통주 전종목을 대순환 단계로 스캔 → store 저장. counts dict 반환.

    universe: 미지정이면 `common_stocks(load_stock_master())`. on_progress(done,total,ticker) 옵션.
    per-item graceful — 종목별 fetch 예외는 그 종목만 stage None + failed 카운트(전체 계속).
    """
    universe = universe if universe is not None else common_stocks(load_stock_master())
    as_of_date = as_of_date or _today_kst()
    total = len(universe)
    rows: list[dict] = []
    counts = {"total": total, "scanned": 0, "with_stage": 0, "failed": 0}
    done = 0

    if universe:
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
            futures = {ex.submit(_fetch_cycle, client, u.get("ticker")): u for u in universe}
            for fut in as_completed(futures):
                stock = futures[fut]
                done += 1
                try:
                    cycle = fut.result()  # dict | None(봉<40·빈 차트)
                except Exception:  # noqa: BLE001 — 종목별 KIS 실패는 삼키지 않되 graceful(그 종목만 None)
                    cycle = None
                    counts["failed"] += 1
                row = _row_from(stock, cycle)
                rows.append(row)
                counts["scanned"] += 1
                if row["stage"] is not None:
                    counts["with_stage"] += 1
                if on_progress is not None:
                    on_progress(done, total, stock.get("ticker"))

    store.upsert_scan(as_of_date, rows)
    counts["as_of_date"] = as_of_date
    counts["stored"] = len(rows)
    return counts


def _main() -> None:
    """엔트리포인트 — env/`__shared__` KIS 자격증명으로 client 확보 → 전종목 스캔 → DB 저장.

    로컬 수동(`uv run python -m stock.screener_scan`) · Cloud Run Job 공용. 진행률 로깅.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from api.detail import resolve_kis_client  # 지연 import(FastAPI/무거운 의존 회피)
    from infra.db import get_sessionmaker, init_db
    from stock.screener_store import ScreenerResultStore

    init_db()  # ScreenerResultRow 테이블 보장(create_all)
    db = get_sessionmaker()()
    try:
        client = resolve_kis_client(None, db).client  # 본인키 없음 → __shared__ → env
    finally:
        db.close()  # client 조립 후 세션은 불필요(store 는 자기 세션)

    store = ScreenerResultStore()

    def _progress(done: int, total: int, ticker: str) -> None:
        if done % 50 == 0 or done == total:
            logger.info("스캔 진행 %d/%d (마지막: %s)", done, total, ticker)

    logger.info("전체 유니버스 대순환 스캔 시작")
    counts = scan_all(client, store, on_progress=_progress)
    logger.info("스캔 완료: %s", counts)


if __name__ == "__main__":
    _main()
