"""KIS 자격증명 암호화(at-rest) — Fernet 대칭 암호. 마스터키는 KIS_ENC_KEY(Secret Manager).

DB엔 **암호문만** 저장하고, KIS 호출 직전에만 복호화한다(복호화 값 로깅·응답 금지).
Fernet = AES128-CBC + HMAC-SHA256(인증) → 위변조 토큰은 복호화 시 예외(InvalidToken).
향후 강화: GCP KMS 엔벨로프 암호화(마스터키를 KMS가 관리).
"""
from __future__ import annotations

from cryptography.fernet import Fernet

from infra.config import kis_encryption_key


def _cipher() -> Fernet:
    # 매 호출마다 현재 마스터키로 구성(테스트가 KIS_ENC_KEY 를 스왑할 수 있게). 구성 비용은 미미.
    return Fernet(kis_encryption_key().encode())


def encrypt(plaintext: str) -> str:
    """평문 → base64 Fernet 토큰(문자열). 값은 로깅하지 않는다."""
    return _cipher().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Fernet 토큰 → 평문. 위변조/키불일치 시 InvalidToken 예외."""
    return _cipher().decrypt(token.encode()).decode()


def mask(value: str | None, keep: int = 2) -> str:
    """상태 표시용 마스킹 — 앞뒤 keep 자만 남기고 가운데는 감춘다(원문 미노출).

    "PSABCDEFGH12" → "PS••••12". 짧으면(≤2*keep) 전체 마스킹. None/빈값 → "".
    """
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "•" * len(value)
    return value[:keep] + "••••" + value[-keep:]
