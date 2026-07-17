"""토큰(질문) 사용량 한도 — 질문 횟수 기반·매일 리셋·관리자 무제한(순수 로직)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from auth.models import DEFAULT_DAILY_LIMIT
from auth.usage import consume, effective_used, is_over_limit, quota_snapshot, today_kst

TODAY = today_kst()


def _user(**kw):
    base = dict(is_admin=False, daily_limit=20, used_today=0, usage_date=None, total_questions=0)
    base.update(kw)
    return SimpleNamespace(**base)


class _DB:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


def test_effective_used_resets_on_new_day():
    assert effective_used(_user(used_today=5, usage_date="1999-01-01")) == 0  # 오늘 아님 → 리셋
    assert effective_used(_user(used_today=5, usage_date=TODAY)) == 5


def test_is_over_limit_admin_exempt():
    assert is_over_limit(_user(is_admin=True, used_today=999, usage_date=TODAY)) is False  # 무제한
    assert is_over_limit(_user(used_today=20, usage_date=TODAY, daily_limit=20)) is True
    assert is_over_limit(_user(used_today=19, usage_date=TODAY, daily_limit=20)) is False


def test_consume_increments_and_commits():
    u = _user(used_today=3, usage_date=TODAY, total_questions=10)
    db = _DB()
    consume(u, db)
    assert u.used_today == 4 and u.total_questions == 11 and db.commits == 1


def test_consume_new_day_resets_then_counts_one():
    u = _user(used_today=20, usage_date="1999-01-01", total_questions=100)
    consume(u, _DB())
    assert u.used_today == 1 and u.usage_date == today_kst() and u.total_questions == 101


def test_quota_snapshot_shape_and_admin_remaining_none():
    s = quota_snapshot(_user(used_today=5, usage_date=TODAY, daily_limit=20))
    assert s == {"is_admin": False, "daily_limit": 20, "used_today": 5, "remaining": 15}
    assert quota_snapshot(_user(is_admin=True, used_today=999, usage_date=TODAY))["remaining"] is None


def test_null_columns_default_defensively():
    # 레거시 행(NULL 컬럼)도 안전하게 기본 처리(마이그레이션 DDL DEFAULT 백필의 belt-and-suspenders).
    u = _user(daily_limit=None, used_today=None, is_admin=None, usage_date=None)
    assert is_over_limit(u) is False  # used 0 < DEFAULT
    assert quota_snapshot(u)["daily_limit"] == DEFAULT_DAILY_LIMIT


def test_get_admin_user_gate():
    from auth.deps import get_admin_user

    admin = _user(is_admin=True)
    assert get_admin_user(admin) is admin
    with pytest.raises(HTTPException) as ei:
        get_admin_user(_user(is_admin=False))
    assert ei.value.status_code == 403
