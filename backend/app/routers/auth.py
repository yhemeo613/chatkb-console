# -*- coding: utf-8 -*-
"""认证：登录 / 注册 / 当前用户（含菜单权限）/ 修改密码"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db, new_id, now
from ..models import Role, User, UserRole
from ..services.security import (create_access_token, get_current_user,
                                 hash_password, load_user_access,
                                 verify_password)

router = APIRouter(prefix="/api/auth", tags=["认证"])


def _token_payload(user: User, db: Session) -> dict:
    access = load_user_access(db, user)
    return {
        "access_token": create_access_token(user.id, user.username),
        "token_type": "bearer",
        "user": {
            "id": user.id, "username": user.username, "nickname": user.nickname,
            "is_superuser": bool(user.is_superuser),
            "roles": access["roles"], "perms": access["perms"], "menus": access["menus"],
        },
    }


@router.post("/register")
def register(body: schemas.RegisterIn, db: Session = Depends(get_db)):
    """开放注册：默认授予「普通用户」角色，注册成功直接登录"""
    username = body.username.strip()
    if len(username) < 3:
        raise HTTPException(400, "用户名至少 3 个字符")
    if len(body.password) < 6:
        raise HTTPException(400, "密码至少 6 位")
    if db.scalar(select(User.id).where(User.username == username)):
        raise HTTPException(400, "用户名已被占用")

    role = db.scalar(select(Role).where(Role.code == "user"))
    if not role:
        raise HTTPException(500, "系统未初始化默认角色")

    user = User(id=new_id(), username=username, nickname=(body.nickname or username).strip(),
                password_hash=hash_password(body.password), is_superuser=0,
                status="active", created_at=now())
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    return _token_payload(user, db)


@router.post("/login", response_model=schemas.TokenOut)
def login(body: schemas.LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username.strip()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    if user.status != "active":
        raise HTTPException(403, "账号已被禁用，请联系管理员")
    user.last_login_at = now()
    db.commit()
    return _token_payload(user, db)


@router.get("/me")
def me(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    u = db.get(User, user["id"])
    if not u or u.status != "active":
        raise HTTPException(401, "账号已被禁用或删除")
    payload = _token_payload(u, db)
    payload["user"]["created_at"] = u.created_at
    payload["user"]["last_login_at"] = u.last_login_at
    return payload["user"]


@router.post("/change-password")
def change_password(body: schemas.ChangePasswordIn,
                    user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    u = db.get(User, user["id"])
    if not verify_password(body.old_password, u.password_hash):
        raise HTTPException(400, "旧密码错误")
    u.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}
