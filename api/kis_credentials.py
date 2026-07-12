"""유저별 KIS 자격증명 등록/조회/삭제 — 등록 시 **검증(토큰 발급)** 후 암호화 저장.

- POST /api/me/kis-credentials {app_key, app_secret, account_no?, acnt_prdt_cd?, env?}
    → 실제 KIS 토큰 발급으로 유효성 검증 → 성공 시만 암호화 저장. 실패 400. 응답 {ok, status}.
- GET  /api/me/kis-credentials → **마스킹 상태만** {registered, source, app_key_masked, account_masked, env}.
- DELETE /api/me/kis-credentials → 유저 키 삭제(이후 공유 fallback). {ok, status}.

안전: 시크릿은 요청 바디로만 수신 → 즉시 암호화(평문 저장·로깅·응답 금지). GET 은 복호화 원문 미반환.
전부 인증 필수(get_current_user). 조회 전용(order/buy/sell 없음).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.deps import get_current_user
from auth.kis_store import KisCredentialStore
from auth.models import User
from collectors.kis import auth as kis_auth
from infra.config import KisConfig
from infra.db import get_db

router = APIRouter()


class KisCredentialsRequest(BaseModel):
    app_key: str = Field(min_length=1)
    app_secret: str = Field(min_length=1)
    account_no: str | None = None
    acnt_prdt_cd: str = "01"
    env: str = "real"


def _validate_kis(app_key: str, app_secret: str, env: str) -> None:
    """실제 KIS 토큰 발급을 1회 시도해 유효성 검증. 실패 시 예외(라우트가 400).

    성공하면 키가 유효. 예외 사유는 키 값을 노출할 수 있어 라우트에서 일반 메시지로 치환한다.
    """
    config = KisConfig(app_key=app_key, app_secret=app_secret, env=env, account_no="")
    kis_auth.request_token(config)


@router.post("/api/me/kis-credentials")
def set_kis_credentials(
    body: KisCredentialsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    env = body.env if body.env in ("real", "demo") else "real"
    try:
        _validate_kis(body.app_key, body.app_secret, env)  # 검증 후 저장(사용자 결정)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="KIS 키 검증 실패 — app_key/app_secret/env(real·demo)를 확인하세요.",
        )
    store = KisCredentialStore(db)
    store.upsert_encrypted(
        str(user.id), body.app_key, body.app_secret, body.account_no, body.acnt_prdt_cd, env
    )
    return {"ok": True, "status": store.status(str(user.id))}


@router.get("/api/me/kis-credentials")
def get_kis_credentials(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """본인 등록 상태(마스킹만) — 복호화 원문 반환 금지."""
    return KisCredentialStore(db).status(str(user.id))


@router.delete("/api/me/kis-credentials")
def delete_kis_credentials(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    store = KisCredentialStore(db)
    store.delete(str(user.id))  # 이후 공유 fallback
    return {"ok": True, "status": store.status(str(user.id))}
