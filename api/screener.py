"""대순환 후보 종목 스크리너 라우트 — GET /api/screener.

시총상위 유니버스를 대순환 단계로 스캔한 후보 목록(**종목명 포함**)을 반환한다. 조회 전용(매매 없음)·
판정=코드(LLM 0). market 화이트리스트 폴백·size clamp·KIS 실패는 **항상 200 graceful**(chart 라우트 패턴).
단계 필터는 프론트가 적용 — 전 유니버스를 단계와 함께 반환한다.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.detail import _resolve_client  # KIS 클라이언트 해석(본인/공유/env·null 흡수) SSOT
from auth.deps import get_current_user_optional
from auth.models import User
from collectors.kis.ranking import MARKET_ISCD
from infra.db import get_db
from stock.screener import screen_grand_cycle

router = APIRouter()

_SIZE_MIN, _SIZE_MAX, _SIZE_DEFAULT = 10, 40, 30


@router.get("/api/screener")
def screener(
    market: str = "all",
    size: int = _SIZE_DEFAULT,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> dict:
    """대순환 단계 후보 스크리너 — 시총상위 유니버스 스캔.

    market: all/kospi/kosdaq/kospi200(화이트리스트 폴백 all) · size: 10~40 clamp.
    랭킹·일봉은 계좌 불필요 → `_resolve_client` 로 client 만 확보(옵션 인증). KIS 실패는 항상 200.
    """
    market = market if market in MARKET_ISCD else "all"
    iscd = MARKET_ISCD[market]
    size = max(_SIZE_MIN, min(size, _SIZE_MAX))
    client = _resolve_client(user, db)
    try:
        result = screen_grand_cycle(client, market_iscd=iscd, size=size)
        result["market"] = market
        return result
    except Exception:  # noqa: BLE001 — KIS/자격증명 실패는 graceful(빈 후보 + partial_failure)
        return {
            "candidates": [], "catalog": None, "market": market, "market_iscd": iscd,
            "size": size, "partial_failure": ["screener"],
            "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
