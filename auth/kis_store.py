"""KisCredentialStore — 유저별 KIS 자격증명의 암호화 저장·해석(SqlWatchlistStore 패턴).

scope_key = str(user.id)(본인) 또는 SHARED_SCOPE("__shared__", 공유 fallback).
`resolve()` = 본인 → 공유 순으로 **복호화된** 자격증명을 돌려준다(호출측이 KIS 클라이언트 조립에 사용).
시크릿은 이 계층에서만 복호화한다 — 로깅·응답 금지. `status()`는 마스킹 값만 반환(복호화 원문 금지).
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from auth.kis_models import KisCredentialRow, _utcnow
from infra.encryption import decrypt, encrypt, mask

SHARED_SCOPE = "__shared__"


@dataclass(frozen=True)
class KisCreds:
    """복호화된 KIS 자격증명(in-memory 전용 — 저장·로깅 금지)."""

    app_key: str
    app_secret: str
    account_no: str  # CANO(하이픈 앞 8자리), 없으면 ""
    acnt_prdt_cd: str
    env: str  # real | demo


def _split_cano(account_no: str | None) -> str:
    """"12345678-01" → "12345678"(CANO). kis_account() 와 동일 파싱."""
    return (account_no or "").split("-", 1)[0].strip()


class KisCredentialStore:
    """요청 스코프 Session 기반 KIS 자격증명 저장소."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def _row(self, scope_key: str) -> KisCredentialRow | None:
        return self._db.scalar(
            select(KisCredentialRow).where(KisCredentialRow.scope_key == scope_key)
        )

    def _decrypt(self, row: KisCredentialRow) -> KisCreds:
        return KisCreds(
            app_key=decrypt(row.app_key_enc),
            app_secret=decrypt(row.app_secret_enc),
            account_no=decrypt(row.account_no_enc) if row.account_no_enc else "",
            acnt_prdt_cd=row.acnt_prdt_cd or "01",
            env=row.env or "real",
        )

    def get_decrypted(self, scope_key: str) -> KisCreds | None:
        row = self._row(scope_key)
        return self._decrypt(row) if row else None

    def resolve(self, user_id: str | None) -> tuple[KisCreds, str] | None:
        """본인(user_id) → 공유(__shared__) 순으로 (자격증명, source) 반환. 둘 다 없으면 None."""
        if user_id:
            row = self._row(str(user_id))
            if row is not None:
                return self._decrypt(row), "user"
        shared = self._row(SHARED_SCOPE)
        if shared is not None:
            return self._decrypt(shared), "shared"
        return None

    def upsert_encrypted(
        self,
        scope_key: str,
        app_key: str,
        app_secret: str,
        account_no: str | None = None,
        acnt_prdt_cd: str = "01",
        env: str = "real",
    ) -> None:
        """자격증명을 암호화해 upsert(created_at 보존, updated_at 갱신). CANO 는 하이픈 앞만 저장."""
        cano = _split_cano(account_no)
        row = self._row(scope_key)
        if row is None:
            row = KisCredentialRow(
                scope_key=scope_key,
                app_key_enc=encrypt(app_key),
                app_secret_enc=encrypt(app_secret),
                account_no_enc=encrypt(cano) if cano else None,
                acnt_prdt_cd=acnt_prdt_cd or "01",
                env=env or "real",
            )
            self._db.add(row)
        else:
            row.app_key_enc = encrypt(app_key)
            row.app_secret_enc = encrypt(app_secret)
            row.account_no_enc = encrypt(cano) if cano else None
            row.acnt_prdt_cd = acnt_prdt_cd or "01"
            row.env = env or "real"
            row.updated_at = _utcnow()
        self._db.commit()

    def delete(self, scope_key: str) -> None:
        row = self._row(scope_key)
        if row is not None:
            self._db.delete(row)
            self._db.commit()

    def status(self, user_id: str | None) -> dict:
        """본인 등록 상태(마스킹만) — 복호화 원문 반환 금지.

        source: "user"(본인 등록) | "shared"(공유 fallback 활성) | "none"(둘 다 없음).
        """
        own = self._row(str(user_id)) if user_id else None
        if own is not None:
            creds = self._decrypt(own)
            return {
                "registered": True,
                "source": "user",
                "app_key_masked": mask(creds.app_key),
                "account_masked": mask(creds.account_no) if creds.account_no else "",
                "env": own.env,
            }
        shared = self._row(SHARED_SCOPE)
        return {
            "registered": False,
            "source": "shared" if shared is not None else "none",
            "app_key_masked": "",
            "account_masked": "",
            "env": "",
        }
