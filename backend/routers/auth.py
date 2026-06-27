"""
用户认证路由 —— 注册、登录、获取当前用户信息。
"""

import hashlib
import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from ..database import get_db
from ..models_db import User
from ..middleware import create_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["认证"])


def _hash_password(password: str) -> str:
    """SHA256 + 随机盐值哈希密码"""
    salt = os.urandom(32).hex()
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${h}"


def _verify_password(password: str, stored: str) -> bool:
    """验证密码是否匹配"""
    salt, h = stored.split("$", 1)
    return h == hashlib.sha256((salt + password).encode()).hexdigest()


# ── 请求/响应模型 ────────────────────────────────────────

class RegisterRequest(BaseModel):
    """注册请求"""
    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=100, description="密码（至少6位）")


class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str


class AuthResponse(BaseModel):
    """认证响应"""
    user_id: int
    username: str
    token: str
    message: str


class UserInfoResponse(BaseModel):
    """用户信息"""
    user_id: int
    username: str
    created_at: str


# ── 路由 ─────────────────────────────────────────────────

@router.post("/register", response_model=AuthResponse)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    """用户注册"""
    # 检查用户名是否已存在
    existing = db.query(User).filter(User.username == body.username).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已被注册")

    # 创建用户
    user = User(
        username=body.username,
        password_hash=_hash_password(body.password),
    )
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
    """用户登录"""
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not _verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    token = create_token(user.id, user.username)
    return AuthResponse(
        user_id=user.id,
        username=user.username,
        token=token,
        message="登录成功",
    )


@router.get("/me", response_model=UserInfoResponse)
def get_me(user: User = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return UserInfoResponse(
        user_id=user.id,
        username=user.username,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )
