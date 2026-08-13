from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware import create_token, get_current_user
from ..models_db import User

router = APIRouter(prefix="/api/auth", tags=["认证"])
logger = logging.getLogger(__name__)

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_CURRENT_HASH_PREFIX = "v2"


def _hash_password(password: str) -> str:
    """Hash a password with a random salt before persisting it."""
    salt = os.urandom(32).hex()
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{_CURRENT_HASH_PREFIX}${salt}${hashed}"


def _verify_password(password: str, stored: object) -> tuple[bool, bool]:
    """Verify only known hash formats without exposing hash data.

    The historical project format was ``<64-hex-salt>$<64-hex-sha256>``.
    It remains supported as a controlled legacy format and is upgraded after a
    successful login. New hashes use the explicit ``v2$`` prefix.
    """
    if not isinstance(stored, str):
        logger.warning("Rejected password hash with a non-string format.")
        return False, False

    parts = stored.split("$")
    if len(parts) == 3 and parts[0] == _CURRENT_HASH_PREFIX:
        _, salt, digest = parts
        needs_upgrade = False
    elif len(parts) == 2:
        salt, digest = parts
        needs_upgrade = True
    else:
        logger.warning("Rejected password hash with an unrecognized format.")
        return False, False

    if not _HEX_64.fullmatch(salt) or not _HEX_64.fullmatch(digest):
        logger.warning("Rejected password hash with an invalid component format.")
        return False, False

    expected_digest = hashlib.sha256((salt + password).encode()).hexdigest()
    return hmac.compare_digest(digest, expected_digest), needs_upgrade


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
    verified, needs_upgrade = _verify_password(body.password, user.password_hash) if user else (False, False)
    if not verified:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误。")

    if needs_upgrade:
        user.password_hash = _hash_password(body.password)
        db.commit()

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
