from __future__ import annotations

import hashlib
import os

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware import create_token, get_current_user
from ..models_db import User

router = APIRouter(prefix="/api/auth", tags=["认证"])


def _hash_password(password: str) -> str:
    """Hash a password with a random salt before persisting it."""
    salt = os.urandom(32).hex()
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${hashed}"


def _verify_password(password: str, stored: str) -> bool:
    """Check whether the provided password matches the stored salted hash."""
    salt, hashed = stored.split("$", 1)
    return hashed == hashlib.sha256((salt + password).encode()).hexdigest()


class RegisterRequest(BaseModel):
    """User registration request."""

    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=100, description="密码，至少 6 位")


class LoginRequest(BaseModel):
    """User login request."""

    username: str
    password: str


class AuthResponse(BaseModel):
    """Authentication response payload."""

    user_id: int
    username: str
    token: str
    message: str


class UserInfoResponse(BaseModel):
    """Current authenticated user information."""

    user_id: int
    username: str
    created_at: str


@router.post("/register", response_model=AuthResponse)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new user and return the initial token."""
    existing_user = db.query(User).filter(User.username == body.username).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在。")

    user = User(username=body.username, password_hash=_hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_token(user.id, user.username)
    return AuthResponse(
        user_id=user.id,
        username=user.username,
        token=token,
        message="注册成功",
    )


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate an existing user and return a token."""
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not _verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误。")

    token = create_token(user.id, user.username)
    return AuthResponse(
        user_id=user.id,
        username=user.username,
        token=token,
        message="登录成功",
    )


@router.get("/me", response_model=UserInfoResponse)
def get_me(user: User = Depends(get_current_user)):
    """Return the current authenticated user."""
    return UserInfoResponse(
        user_id=user.id,
        username=user.username,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )
