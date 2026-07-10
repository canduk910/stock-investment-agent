"""잔고(포트폴리오) 라우트 — plan §Phase B 백엔드.

GET /api/balance 하나로 단일 로컬 사용자 계좌의 보유종목·요약을 반환한다.
KIS inquire_balance 어댑터(MCP 검증, TTTC8434R/VTTC8434R)를 재사용하고, 정규화는
collectors.kis.normalize.normalize_balance 가 담당한다(어댑터 안쪽).

## 계약(frontend 의존 — 임의 변경 금지)
GET /api/balance → {
  holdings:[{ticker,name,qty,avg_price,current_price,eval_amount,pnl_amount,pnl_pct}],
  summary:{deposit,purchase_amount,eval_amount,pnl_amount,total_eval,net_asset},
  partial_failure:[],
}
(holdings/summary shape 은 normalize_balance 반환과 일치. 실패 시 둘 다 None + partial_failure=['balance'].)

## 안전·정책
- **조회 전용**(order/buy/sell 없음). GET 만 노출한다.
- 현재가(prpr) 포함 → **캐시 저장 없음**(원칙1). inquire_balance 에도 cache 인자가 없다.
- KIS 실패는 graceful: 항상 200, partial_failure 에 'balance', holdings/summary=None
  (한 소스 실패가 프론트 전체를 죽이지 않는다 — 번들 partial_failure 철학).

api.detail 의 _build_kis_client 를 재사용(순환 회피 — detail 은 api.main 미참조).
라우터 wiring(api.main include)은 리더 전담.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

# api.detail 재사용(순환 회피 — detail 은 api.main 을 import 하지 않으므로 사이클 없음).
from api.detail import _build_kis_client
from collectors.kis import balance as kis_balance
from infra import config as infra_config

router = APIRouter()

_log = logging.getLogger(__name__)


def _load_account() -> tuple[str, str]:
    """계좌번호(CANO)·상품코드(ACNT_PRDT_CD)를 config 에서 로드(단일 로컬 사용자).

    SSOT 는 infra.config.kis_account() — 폴백·기본값 규칙은 거기 단일 출처.
    테스트는 이 함수를 monkeypatch → 실 .env 를 타지 않는다.
    """
    return infra_config.kis_account()


@router.get("/api/balance")
def get_balance() -> dict:
    """계좌 보유종목·요약(조회 전용). KIS 실패는 partial_failure 로 graceful(항상 200)."""
    cano, prdt = _load_account()
    client = _build_kis_client()
    try:
        result = kis_balance.inquire_balance(client, cano, prdt)
    except Exception:
        # KIS 조회 실패(오류 표면화 KisApiError·네트워크 등)를 삼키지 않고 partial_failure
        # 로 기록한다(§5 금지: except pass). 프론트는 이 리스트로 "일시 조회 불가"를 표시.
        _log.warning("balance inquiry failed", exc_info=True)
        return {"holdings": None, "summary": None, "partial_failure": ["balance"]}
    return {
        "holdings": result.get("holdings"),
        "summary": result.get("summary"),
        "partial_failure": [],
    }
