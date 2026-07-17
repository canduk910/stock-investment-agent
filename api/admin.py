"""관리자 라우터 — 유저 관리·이용 통계·질문 한도 제어. 전 라우트 `get_admin_user` 게이트(비관리자 403).

GET    /api/admin/users                    → [{id,email,is_admin,daily_limit,used_today,remaining,total_questions,created_at}]
PATCH  /api/admin/users/{id} {is_admin?, daily_limit?} → 바디에 온 필드만 부분 갱신
POST   /api/admin/users/{id}/reset-usage   → 오늘 사용량(used_today) 0 리셋
DELETE /api/admin/users/{id}               → 유저 + 스코프 데이터 삭제(자기 자신 삭제 방지 400)

**안전**: 매매·자격증명 원문 노출 없음(비밀번호 해시·KIS 암호문 미반환). 자기 자신 관리자 해제/삭제는
락아웃 방지로 400. 유저 삭제 시 그 유저의 관심종목·대화기록·KIS 자격증명(암호문)까지 함께 정리(고아 방지).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth.deps import get_admin_user
from auth.models import User
from auth.usage import quota_snapshot, today_kst
from infra.db import get_db

router = APIRouter()


def _admin_user_view(user: User) -> dict:
    """관리자 목록/응답용 유저 표현 — 비밀번호 해시·KIS 원문은 절대 포함하지 않는다.
    quota_snapshot(오늘 리셋 반영) + 누적 통계(total_questions) + 가입일."""
    snap = quota_snapshot(user)
    return {
        "id": user.id,
        "email": user.email,
        "is_admin": snap["is_admin"],
        "daily_limit": snap["daily_limit"],
        "used_today": snap["used_today"],
        "remaining": snap["remaining"],  # 관리자는 None(무제한)
        "total_questions": user.total_questions or 0,
        "created_at": user.created_at,  # FastAPI 인코더가 ISO 문자열로 직렬화
    }


class UpdateUserRequest(BaseModel):
    is_admin: bool | None = None
    daily_limit: int | None = Field(default=None, ge=0)  # 음수 한도 금지


def _get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return user


@router.get("/api/admin/users")
def list_users(admin: User = Depends(get_admin_user), db: Session = Depends(get_db)) -> dict:
    """전체 유저 + 이용 통계(관리자 전용). 가입 최신순."""
    users = db.scalars(select(User).order_by(User.created_at.desc())).all()
    return {"users": [_admin_user_view(u) for u in users]}


@router.patch("/api/admin/users/{user_id}")
def update_user(
    user_id: int,
    body: UpdateUserRequest,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> dict:
    """is_admin·daily_limit 부분 갱신(바디에 온 필드만). 자기 자신 관리자 해제는 락아웃 방지 400."""
    user = _get_user_or_404(db, user_id)
    fields = body.model_fields_set
    if "is_admin" in fields:
        if user.id == admin.id and not body.is_admin:
            raise HTTPException(status_code=400, detail="자기 자신의 관리자 권한은 해제할 수 없습니다.")
        user.is_admin = bool(body.is_admin)
    if "daily_limit" in fields and body.daily_limit is not None:
        user.daily_limit = int(body.daily_limit)
    db.commit()
    db.refresh(user)
    return _admin_user_view(user)


@router.post("/api/admin/users/{user_id}/reset-usage")
def reset_usage(
    user_id: int, admin: User = Depends(get_admin_user), db: Session = Depends(get_db)
) -> dict:
    """오늘 사용량을 즉시 0으로 리셋(usage_date=오늘). 매일 자동 리셋과 별개의 수동 제어."""
    user = _get_user_or_404(db, user_id)
    user.used_today = 0
    user.usage_date = today_kst()
    db.commit()
    db.refresh(user)
    return _admin_user_view(user)


def _purge_user_data(db: Session, user_id: int) -> None:
    """유저 삭제 전 스코프 데이터 정리(고아 방지). 관심종목·대화기록(+메시지 cascade)·KIS 자격증명."""
    from auth.kis_models import KisCredentialRow
    from chat.history_models import Conversation
    from watchlist.db_models import WatchlistItemRow

    scope = str(user_id)  # 유저별 데이터 스코프 키는 str(user.id)
    db.query(WatchlistItemRow).filter(WatchlistItemRow.user_id == scope).delete(
        synchronize_session=False
    )
    db.query(KisCredentialRow).filter(KisCredentialRow.scope_key == scope).delete(
        synchronize_session=False
    )
    # 대화는 ORM delete 로 지워 relationship cascade(delete-orphan)가 메시지까지 정리(DB무관).
    for conv in db.scalars(select(Conversation).where(Conversation.user_id == scope)).all():
        db.delete(conv)


@router.delete("/api/admin/users/{user_id}")
def delete_user(
    user_id: int, admin: User = Depends(get_admin_user), db: Session = Depends(get_db)
) -> dict:
    """유저 + 스코프 데이터 삭제. 자기 자신 삭제는 락아웃 방지 400."""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="자기 자신의 계정은 삭제할 수 없습니다.")
    user = _get_user_or_404(db, user_id)
    _purge_user_data(db, user_id)
    db.delete(user)
    db.commit()
    return {"ok": True, "deleted": user_id}
