"""인증 라우터 — 회원가입/로그인/내정보. bcrypt 해시 + JWT.

POST /api/auth/signup {email, password} → {token, user:{id,email}} (email 중복=409, 약한 입력=422)
POST /api/auth/login  {email, password} → {token, user} (불일치=401)
GET  /api/auth/me     (Bearer)           → {id, email}
비밀번호 해시만 저장·응답에 절대 노출하지 않는다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth.deps import get_current_user
from auth.models import User
from auth.security import create_access_token, hash_password, verify_password
from auth.usage import quota_snapshot
from infra.db import get_db

router = APIRouter()


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)  # 최소 8자


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def _user_public(user: User) -> dict:
    """응답용 유저 표현 — 해시는 절대 포함하지 않는다. is_admin·오늘 질문 잔량(quota) 포함
    (프론트가 관리자 UI 노출·질문 잔량 표시에 사용)."""
    return {"id": user.id, "email": user.email, **quota_snapshot(user)}


@router.post("/api/auth/signup")
def signup(body: SignupRequest, db: Session = Depends(get_db)) -> dict:
    email = body.email.lower()
    exists = db.scalar(select(User).where(User.email == email))
    if exists is not None:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"token": create_access_token(user.id), "user": _user_public(user)}


@router.post("/api/auth/login")
def login(body: LoginRequest, db: Session = Depends(get_db)) -> dict:
    email = body.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
    return {"token": create_access_token(user.id), "user": _user_public(user)}


@router.get("/api/auth/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return _user_public(user)
