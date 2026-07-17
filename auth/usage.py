"""토큰(질문) 사용량 한도 — 질문 횟수 기반, 매일(KST) 리셋. 관리자는 무제한(차단 면제).

- 챗 1턴 = 1회 소비. 관리자 제외 계정은 `daily_limit`(기본 20) 초과 시 차단.
- **매일 리셋**: `usage_date`(집계 기준일, KST YYYY-MM-DD)가 오늘이 아니면 used_today 는 사실상 0.
  실제 리셋+커밋은 소비 시점(consume)에서 반영한다(읽기[snapshot]는 미커밋으로 today 반영만).
- 레거시 행(NULL 컬럼)도 방어적으로 기본값 처리(마이그레이션 DDL DEFAULT 로 백필하지만 belt-and-suspenders).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from auth.models import DEFAULT_DAILY_LIMIT, User

_KST = timezone(timedelta(hours=9))


def today_kst() -> str:
    """오늘 날짜(KST) 'YYYY-MM-DD'. 리셋 경계 = 한국 자정."""
    return datetime.now(_KST).strftime("%Y-%m-%d")


def _limit(user: User) -> int:
    return user.daily_limit if user.daily_limit is not None else DEFAULT_DAILY_LIMIT


def effective_used(user: User, today: str | None = None) -> int:
    """오늘 기준 사용량 — usage_date 가 오늘이 아니면 0(리셋 반영, 미커밋)."""
    today = today or today_kst()
    if user.usage_date != today:
        return 0
    return user.used_today or 0


def is_over_limit(user: User, today: str | None = None) -> bool:
    """관리자 제외, 오늘 사용량이 한도 이상이면 True(선차단)."""
    if user.is_admin:
        return False
    return effective_used(user, today) >= _limit(user)


def consume(user: User, db, today: str | None = None) -> None:
    """한 턴 소비 기록(일별 리셋 반영 + 누적 + 커밋). 관리자도 통계는 세되 차단만 면제된다."""
    today = today or today_kst()
    if user.usage_date != today:  # 날짜 경계 넘음 → 오늘치 리셋
        user.used_today = 0
        user.usage_date = today
    user.used_today = (user.used_today or 0) + 1
    user.total_questions = (user.total_questions or 0) + 1
    db.commit()


def quota_snapshot(user: User, today: str | None = None) -> dict:
    """프론트 표시용 스냅샷 — {is_admin, daily_limit, used_today, remaining}. 관리자 remaining=None(무제한)."""
    used = effective_used(user, today)
    limit = _limit(user)
    return {
        "is_admin": bool(user.is_admin),
        "daily_limit": limit,
        "used_today": used,
        "remaining": None if user.is_admin else max(0, limit - used),
    }
