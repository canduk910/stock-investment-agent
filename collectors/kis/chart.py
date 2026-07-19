"""국내주식기간별시세(일/주/월/년) 어댑터 — MCP 검증 inquire_daily_itemchartprice(FHKST03010100).

일봉은 확정 과거 데이터라 조건부 캐시 가능(현재가 아님). 캐시 배선은 T8에서 정책 경유.
"""
from __future__ import annotations

import datetime as _dt

from collectors.kis import normalize

API_PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
TR_ID = "FHKST03010100"  # real/demo 동일

# KIS 는 한 호출당 ~100 레코드만 주고 연속 토큰이 없다(라이브 확인) → 장기간은 date-window 후진 반복.
_DEFAULT_MAX_BARS = 3000  # 10년 일봉(~2500)까지 여유
_DEFAULT_MAX_PAGES = 40   # 안전 상한(무한루프·과호출 방지)


def inquire_daily_itemchartprice(
    client,
    ticker: str,
    start_date: str,
    end_date: str,
    period: str = "D",
    adj_price: str = "1",
    market: str = "J",
) -> dict:
    """기간별 시세(캔들) 조회 → {ticker, candles:[...]}. 단일 호출(~100 상한)."""
    params = {
        "FID_COND_MRKT_DIV_CODE": market,
        "FID_INPUT_ISCD": ticker,
        "FID_INPUT_DATE_1": start_date,
        "FID_INPUT_DATE_2": end_date,
        "FID_PERIOD_DIV_CODE": period,  # D:일 W:주 M:월 Y:년
        "FID_ORG_ADJ_PRC": adj_price,   # 0:수정주가 1:원주가
    }
    body = client.get(TR_ID, API_PATH, params)
    return normalize.normalize_daily_chart(body)


def _prev_day(date_str: str) -> str:
    """YYYYMMDD 하루 전(페이지네이션 커서 후진용)."""
    d = _dt.datetime.strptime(date_str, "%Y%m%d").date() - _dt.timedelta(days=1)
    return d.strftime("%Y%m%d")


def fetch_chart_series(
    client,
    ticker: str,
    *,
    period: str = "D",
    start_date: str,
    end_date: str,
    adj_price: str = "0",
    market: str = "J",
    max_bars: int = _DEFAULT_MAX_BARS,
    max_pages: int = _DEFAULT_MAX_PAGES,
) -> dict:
    """[start_date, end_date] 전 구간 캔들 — **~100/호출 상한을 date-window 후진 페이지네이션**으로 넘는다.

    KIS 는 연속 토큰이 없어 `end` 를 '가장 오래된 수신일 직전'으로 당겨 반복 호출하고 병합·정렬한다.
    종료: oldest ≤ start_date(구간 소진) · 새 캔들 0(무진행) · max_bars/max_pages 캡. 무한루프 방지.
    반환은 `inquire_daily_itemchartprice` 와 동일 계약 `{ticker, candles:[...date 오름차순]}`.
    """
    by_date: dict[str, dict] = {}
    cursor_end = end_date
    for _ in range(max_pages):
        page = inquire_daily_itemchartprice(
            client, ticker, start_date, cursor_end,
            period=period, adj_price=adj_price, market=market,
        )
        candles = [c for c in (page.get("candles") or []) if c.get("date")]
        if not candles:
            break
        before = len(by_date)
        for c in candles:
            by_date.setdefault(c["date"], c)  # 겹치는 날짜는 최신 페이지 값 유지(동일해야 정상)
        oldest = min(c["date"] for c in candles)
        # 구간을 다 덮었거나, 진행이 없거나(무한루프 방지), 캡 도달이면 종료.
        if oldest <= start_date or len(by_date) == before or len(by_date) >= max_bars:
            break
        cursor_end = _prev_day(oldest)

    rows = sorted(
        (c for d, c in by_date.items() if d >= start_date), key=lambda c: c["date"]
    )
    if len(rows) > max_bars:
        rows = rows[-max_bars:]  # 최근 max_bars 만(안전)
    return {"ticker": ticker, "candles": rows}
