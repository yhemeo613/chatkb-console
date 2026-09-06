# -*- coding: utf-8 -*-
"""账号管理：用户 CRUD / 角色分配 / 重置密码 / 启停"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db, new_id, now
from ..models import Role, User, UserRole
from ..services.security import get_current_user, hash_password, require_perm

router = APIRouter(prefix="/api/system/users", tags=["账号管理"])

PAGE_PERMS = [Depends(get_current_user), Depends(require_perm("sys:user"))]


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    nickname: str = Field(default="", max_length=64)
    role_ids: list[str] = []
    status: str = "active"


class UserUpdate(BaseModel):
    nickname: str | None = None
    role_ids: list[str] | None = None
    status: str | None = None


class ResetPwdIn(BaseModel):
    new_password: str = Field(min_length=6, max_length=128)


def _roles_of(db: Session, user_id: str) -> list[dict]:
    roles = db.scalars(select(Role).join(UserRole, UserRole.role_id == Role.id)
                       .where(UserRole.user_id == user_id)).all()
    return [{"id": r.id, "code": r.code, "name": r.name} for r in roles]


def _user_dict(db: Session, u: User) -> dict:
    return {
        "id": u.id, "username": u.username, "nickname": u.nickname,
        "is_superuser": bool(u.is_superuser), "status": u.status,
        "roles": _roles_of(db, u.id),
        "last_login_at": u.last_login_at, "created_at": u.created_at,
    }


@router.get("", dependencies=PAGE_PERMS)
def list_users(keyword: str = "", page: int = 1, size: int = 20, db: Session = Depends(get_db)):
    q = select(User)
    if keyword.strip():
        kw = f"%{keyword.strip()}%"
        q = q.where(or_(User.username.like(kw), User.nickname.like(kw)))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(User.created_at).offset((page - 1) * size).limit(size)).all()
    return {"total": total, "items": [_user_dict(db, u) for u in rows]}


@router.post("", dependencies=[Depends(get_current_user), Depends(require_perm("sys:user:create"))])
def create_user(body: UserCreate, db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(User.username == body.username.strip())):
        raise HTTPException(400, "用户名已存在")
    user = User(id=new_id(), username=body.username.strip(),
                nickname=(body.nickname or body.username).strip(),
                password_hash=hash_password(body.password),
                is_superuser=0, status=body.status if body.status in ("active", "disabled") else "active",
                created_at=now())
    db.add(user)
    db.flush()
    for rid in set(body.role_ids):
        if db.get(Role, rid):
            db.add(UserRole(user_id=user.id, role_id=rid))
    db.commit()
    return _user_dict(db, user)


@router.put("/{user_id}", dependencies=[Depends(get_current_user), Depends(require_perm("sys:user:update"))])
def update_user(user_id: str, body: UserUpdate, db: Session = Depends(get_db),
                current: dict = Depends(get_current_user)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "账号不存在")
    if user.id == current["id"] and body.status == "disabled":
        raise HTTPException(400, "不能停用自己")
    if body.nickname is not None:
        user.nickname = body.nickname.strip()
    if body.status in ("active", "disabled"):
        user.status = body.status
    if body.role_ids is not None:
        db.query(UserRole).filter(UserRole.user_id == user_id).delete()
        for rid in set(body.role_ids):
            if db.get(Role, rid):
                db.add(UserRole(user_id=user_id, role_id=rid))
    db.commit()
    return _user_dict(db, user)


@router.put("/{user_id}/reset-password",
            dependencies=[Depends(get_current_user), Depends(require_perm("sys:user:reset_pwd"))])
def reset_password(user_id: str, body: ResetPwdIn, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "账号不存在")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}


@router.delete("/{user_id}", dependencies=[Depends(get_current_user), Depends(require_perm("sys:user:delete"))])
def delete_user(user_id: str, db: Session = Depends(get_db), current: dict = Depends(get_current_user)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "账号不存在")
    if user.is_superuser:
        raise HTTPException(400, "不能删除超级管理员")
    if user.id == current["id"]:
        raise HTTPException(400, "不能删除自己")
    db.query(UserRole).filter(UserRole.user_id == user_id).delete()
    db.delete(user)
    db.commit()
    return {"ok": True}
