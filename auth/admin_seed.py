"""관리자 부트스트랩 시드 — 설정된 이메일의 기존 유저를 is_admin=True 로 승격(startup, idempotent).

`infra.config.admin_emails()`(env ADMIN_EMAILS, 기본 dukkikim@yonsei.ac.kr)의 각 이메일에 대해,
**이미 가입한** 유저면 관리자로 승격한다. 계정을 만들지 않고(가입은 사용자 몫), 없으면 no-op —
그 유저가 가입/재기동 후 다음 startup 에 승격된다. graceful(시드 실패가 앱 기동을 막지 않는다).
"""
from __future__ import annotations

import logging

_log = logging.getLogger(__name__)


def seed_admins(session_factory=None) -> int:
    """ADMIN_EMAILS 의 기존 유저를 is_admin=True 로 승격. 승격한 수 반환(idempotent)."""
    from sqlalchemy import select

    from auth.models import User
    from infra.config import admin_emails
    from infra.db import get_sessionmaker

    emails = admin_emails()
    if not emails:
        return 0
    SessionLocal = session_factory or get_sessionmaker()
    db = SessionLocal()
    promoted = 0
    try:
        for email in emails:
            user = db.scalar(select(User).where(User.email == email))
            if user is not None and not user.is_admin:
                user.is_admin = True
                promoted += 1
        if promoted:
            db.commit()
            _log.info("seeded %d admin(s): %s", promoted, ", ".join(emails))
    except Exception:  # 시드 실패는 기동을 막지 않는다(권한은 API 로도 부여 가능)
        _log.warning("admin seed failed", exc_info=True)
    finally:
        db.close()
    return promoted
