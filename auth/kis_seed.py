"""공유(__shared__) KIS 자격증명 1회 시드 — env KIS_* → 암호화 DB 행(프로덕션 전환용).

프로덕션은 KIS 앱키를 Secret Manager 에서 제거하고 DB 암호화 저장으로 옮긴다. 전환 절차:
  ① KIS_ENC_KEY 등록 → ② env KIS_* 유지한 채 배포(startup 이 이 함수로 __shared__ 시드) →
  ③ Secret Manager 에서 KIS_* 제거·재배포(env 없음, __shared__ 행 잔존).

idempotent: __shared__ 행이 이미 있으면 스킵. env KIS_* 없으면(로컬은 .env fallback 이 3순위) 스킵.
실패는 graceful(앱 기동을 막지 않음 — 시드 없으면 resolve 가 env fallback 을 쓴다). 값 로깅 없음.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def seed_shared_kis_from_env() -> bool:
    """env KIS_* 를 __shared__ 암호화 행으로 시드(idempotent). 시드하면 True, 스킵/실패면 False."""
    try:
        from infra.config import ConfigError, KisConfig, kis_account

        try:
            config = KisConfig.load()  # env KIS_APP_KEY/SECRET 필요
        except ConfigError:
            return False  # env 키 없음 → 시드 스킵

        from auth.kis_store import SHARED_SCOPE, KisCredentialStore
        from infra.db import get_sessionmaker

        db = get_sessionmaker()()
        try:
            store = KisCredentialStore(db)
            if store.get_decrypted(SHARED_SCOPE) is not None:
                return False  # 이미 시드됨
            cano, prdt = kis_account()
            store.upsert_encrypted(
                SHARED_SCOPE, config.app_key, config.app_secret, cano, prdt, config.env
            )
            logger.info("공유 KIS 자격증명(__shared__) 시드 완료(env → 암호화 DB)")
            return True
        finally:
            db.close()
    except Exception:  # 시드 실패는 기동을 막지 않는다(env fallback 존재)
        logger.warning("공유 KIS 자격증명 시드 실패(무시, env fallback 사용)", exc_info=True)
        return False
