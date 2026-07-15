"""잔고(포트폴리오) 라우트 — plan §Phase B 백엔드.

GET /api/balance 하나로 단일 로컬 사용자 계좌의 보유종목·요약을 반환한다.
KIS inquire_balance 어댑터(MCP 검증, TTTC8434R/VTTC8434R)를 재사용하고, 정규화는
collectors.kis.normalize.normalize_balance 가 담당한다(어댑터 안쪽).

## 계약(frontend 의존 — 임의 변경 금지)
GET /api/balance → {
  holdings:[{ticker,name,qty,avg_price,current_price,eval_amount,pnl_amount,pnl_pct,spark}],
  summary:{deposit,purchase_amount,eval_amount,pnl_amount,total_eval,net_asset},
  partial_failure:[],
}
(holdings/summary shape 은 normalize_balance 반환과 일치. spark=number[]|null 은 관심종목과 동일한
 미니 스파크라인[일봉 종가 시계열]으로, 라우트가 후처리로 얹는다[실패는 spark=None, partial_failure 미오염].
 실패 시 holdings/summary 둘 다 None + partial_failure=['balance'].)

## 안전·정책
- **조회 전용**(order/buy/sell 없음). GET 만 노출한다.
- 현재가(prpr) 포함 → **캐시 저장 없음**(원칙1). inquire_balance 에도 cache 인자가 없다.
- KIS 실패는 graceful: 항상 200, partial_failure 에 'balance', holdings/summary=None
  (한 소스 실패가 프론트 전체를 죽이지 않는다 — 번들 partial_failure 철학).

계좌·자격증명은 **유저별**: 로그인+등록 시 본인 KIS 키/계좌, 아니면 공유 fallback(→env, 로컬).
`api.detail.resolve_kis_client(user, db)` 가 (client, cano, prdt) 를 해석한다. 옵션 인증
(get_current_user_optional)이라 **비로그인도 공개 조회**(공유 계좌) — 게이트 아님.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

# api.detail 재사용(순환 회피 — detail 은 api.main 을 import 하지 않으므로 사이클 없음).
from api.detail import NoKisCredentials, resolve_kis_client
from auth.deps import get_current_user_optional
from auth.models import User
from collectors.kis import balance as kis_balance
from infra.db import get_db
# 관심종목과 동일한 미니 스파크라인(일봉 종가 시계열) — 공용 조회(현재가 캐시 금지·per-item graceful).
from watchlist.service import fetch_sparks_parallel

router = APIRouter()

_log = logging.getLogger(__name__)


@router.get("/api/balance")
def get_balance(
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> dict:
    """계좌 보유종목·요약(조회 전용). 자격증명 없음·KIS 실패는 graceful(항상 200)."""
    try:
        resolved = resolve_kis_client(user, db)  # 본인 등록키 → 공유 → env
    except NoKisCredentials:
        return {"holdings": None, "summary": None, "partial_failure": ["balance"]}
    try:
        result = kis_balance.inquire_balance(resolved.client, resolved.cano, resolved.prdt)
    except Exception:
        # KIS 조회 실패(오류 표면화 KisApiError·네트워크 등)를 삼키지 않고 partial_failure
        # 로 기록한다(§5 금지: except pass). 프론트는 이 리스트로 "일시 조회 불가"를 표시.
        _log.warning("balance inquiry failed", exc_info=True)
        return {"holdings": None, "summary": None, "partial_failure": ["balance"]}

    # 각 보유종목에 미니 스파크라인(관심종목과 동일 로직)을 얹는다 — 선택적 시각화라 실패는 조용히
    # spark=None(시세는 이미 있음). 스파크 실패가 partial_failure 를 오염시키지 않는다(원칙: 독립).
    holdings = result.get("holdings") or []
    if holdings:
        try:
            sparks = fetch_sparks_parallel(resolved.client, [h["ticker"] for h in holdings])
        except Exception:
            _log.warning("balance spark fetch failed", exc_info=True)
            sparks = {}
        for h in holdings:
            h["spark"] = sparks.get(h["ticker"])

    return {
        "holdings": result.get("holdings"),
        "summary": result.get("summary"),
        "partial_failure": [],
    }
