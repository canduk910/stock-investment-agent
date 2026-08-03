"""대순환 후보 종목 스크리너 라우트 — GET /api/screener.

두 서빙 경로:
- **scope=cached(기본)**: 배치 스캐너(`stock/screener_scan.py`)가 매일 저장한 **한국시장 전체 보통주**
  스캔 결과(`ScreenerResultStore`)를 반환한다 — 전 유니버스(~2천 종목)를 단계와 함께. DB 가 비어
  있으면(첫 스캔 전) **live top-N 로 폴백**해 화면이 절대 빈손이 아니게 한다.
- **scope=live**: 시총상위 top-N 을 요청 시 라이브 스캔(빠른 조회, 하위호환).

조회 전용(매매 없음)·판정=코드(LLM 0). market 화이트리스트 폴백·size clamp·KIS 실패는 **항상 200
graceful**(chart 라우트 패턴). **단계 필터는 프론트가 적용** — 전 유니버스를 단계와 함께 반환한다.
**현재가/등락률은 cached 에 없다**(무캐시 원칙1 — 클릭 시 종목 상세가 라이브 조회).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.detail import _resolve_client  # KIS 클라이언트 해석(본인/공유/env·null 흡수) SSOT
from auth.deps import get_current_user_optional
from auth.models import User
from collectors.kis.ranking import MARKET_ISCD
from infra.db import get_db
from infra.timeutil import now_iso  # as_of 타임스탬프 — timeutil SSOT(인라인 datetime 조립 제거)
from stock.constants import INDICATOR_CONFIG
from stock.screener import screen_grand_cycle
from stock.screener_store import default_store

router = APIRouter()

_SIZE_MIN, _SIZE_MAX, _SIZE_DEFAULT = 10, 40, 30
_SCOPES = {"cached", "live"}
# 사용자 market → 저장 행의 market 값. all/kospi200 은 행 필터 없음(kospi200 은 cached 미지원 → live 폴백).
_ROW_MARKET = {"kospi": "KOSPI", "kosdaq": "KOSDAQ"}


def _get_store():
    """스캔 결과 스토어(테스트 monkeypatch 경계). 앱 기본 세션팩토리 싱글턴."""
    return default_store()


def _cached_result(market: str, iscd: str) -> dict | None:
    """DB 최신 스캔 결과 → cached 응답. DB 비었거나 cached 미지원(kospi200)이면 None(→ live 폴백).

    후보(candidates) = stage 판정된 종목만(stage None 은 봉<40·조회실패라 후보 제외). universe_size 는
    None 포함 전체(스캔 대상 수). 단계 필터는 프론트가 적용 — 전 단계를 반환.
    """
    if market == "kospi200":
        return None  # 마스터에 편입정보 없음 → cached 재현 불가(live 폴백)
    store = _get_store()
    as_of = store.latest_as_of()
    if as_of is None:
        return None  # 첫 스캔 전 → live 폴백
    rows = store.list_results(as_of_date=as_of, market=_ROW_MARKET.get(market))
    candidates = [r for r in rows if r.get("stage") is not None]
    return {
        "candidates": candidates,
        "catalog": INDICATOR_CONFIG.get("grand_cycle"),  # 6단계 라벨 SSOT → 프론트 전파
        "market": market,
        "market_iscd": iscd,
        "scope": "cached",
        "as_of": as_of,               # 스캔일 "YYYY-MM-DD"
        "total": len(candidates),     # 후보(stage 판정) 수
        "universe_size": len(rows),   # 스캔 대상 수(None 포함)
        "partial_failure": [],
    }


def _live_result(client, market: str, iscd: str, size: int) -> dict:
    """시총상위 top-N 라이브 스캔. KIS 실패는 항상 graceful(빈 후보 + partial_failure)."""
    try:
        result = screen_grand_cycle(client, market_iscd=iscd, size=size)
        result["market"] = market
        result["scope"] = "live"
        result["total"] = len(result.get("candidates") or [])
        result["universe_size"] = result["total"]
        return result
    except Exception:  # noqa: BLE001 — KIS/자격증명 실패는 graceful(빈 후보 + partial_failure)
        return {
            "candidates": [], "catalog": None, "market": market, "market_iscd": iscd,
            "scope": "live", "size": size, "total": 0, "universe_size": 0,
            "partial_failure": ["screener"], "as_of": now_iso(),
        }


@router.get("/api/screener")
def screener(
    market: str = "all",
    size: int = _SIZE_DEFAULT,
    scope: str = "cached",
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> dict:
    """대순환 단계 후보 스크리너.

    market: all/kospi/kosdaq/kospi200(화이트리스트 폴백 all) · size: 10~40 clamp(live 전용) ·
    scope: cached(기본, 전체 유니버스 DB)/live(top-N 라이브). cached 인데 DB 비었으면 live 폴백.
    랭킹·일봉은 계좌 불필요 → `_resolve_client` 로 client 만 확보(옵션 인증). KIS 실패는 항상 200.
    """
    market = market if market in MARKET_ISCD else "all"
    iscd = MARKET_ISCD[market]
    size = max(_SIZE_MIN, min(size, _SIZE_MAX))
    scope = scope if scope in _SCOPES else "cached"

    if scope == "cached":
        cached = _cached_result(market, iscd)
        if cached is not None:
            return cached
        # DB 비었거나 kospi200(미지원) → live 폴백(화면이 빈손 아니게)

    return _live_result(_resolve_client(user, db), market, iscd, size)
