# -*- coding: utf-8 -*-
"""角色管理：角色 CRUD + 菜单/权限授权"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db, new_id, now
from ..models import Menu, Role, RoleMenu, User, UserRole
from ..services.security import get_current_user, require_perm

router = APIRouter(prefix="/api/system/roles", tags=["角色管理"])

PAGE_PERMS = [Depends(get_current_user), Depends(require_perm("sys:role"))]


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=2, max_length=64)
    description: str = ""
    menu_ids: list[str] = []


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    menu_ids: list[str] | None = None


@router.get("", dependencies=PAGE_PERMS)
def list_roles(db: Session = Depends(get_db)):
    out = []
    for r in db.scalars(select(Role).order_by(Role.created_at)):
        menu_ids = list(db.scalars(select(RoleMenu.menu_id).where(RoleMenu.role_id == r.id)))
        user_count = db.scalar(select(func.count()).select_from(
            select(UserRole.user_id).where(UserRole.role_id == r.id).subquery()))
        out.append({"id": r.id, "name": r.name, "code": r.code, "description": r.description,
                    "is_builtin": bool(r.is_builtin), "user_count": user_count,
                    "menu_ids": menu_ids, "created_at": r.created_at})
    return out


@router.post("", dependencies=[Depends(get_current_user), Depends(require_perm("sys:role:create"))])
def create_role(body: RoleCreate, db: Session = Depends(get_db)):
    code = body.code.strip()
    if db.scalar(select(Role.id).where(Role.code == code)):
        raise HTTPException(400, "角色编码已存在")
    role = Role(id=new_id(), name=body.name.strip(), code=code,
                description=body.description.strip(), is_builtin=0, created_at=now())
    db.add(role)
    db.flush()
    db.add_all([RoleMenu(role_id=role.id, menu_id=mid) for mid in set(body.menu_ids)
                if db.get(Menu, mid)])
    db.commit()
    return {"id": role.id}


@router.put("/{role_id}", dependencies=[Depends(get_current_user), Depends(require_perm("sys:role:update"))])
def update_role(role_id: str, body: RoleUpdate, db: Session = Depends(get_db)):
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(404, "角色不存在")
    if body.name is not None:
        role.name = body.name.strip()
    if body.description is not None:
        role.description = body.description.strip()
    if body.menu_ids is not None:
        db.query(RoleMenu).filter(RoleMenu.role_id == role_id).delete()
        db.add_all([RoleMenu(role_id=role_id, menu_id=mid) for mid in set(body.menu_ids)
                    if db.get(Menu, mid)])
    db.commit()
    return {"ok": True}


@router.delete("/{role_id}", dependencies=[Depends(get_current_user), Depends(require_perm("sys:role:delete"))])
def delete_role(role_id: str, db: Session = Depends(get_db)):
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(404, "角色不存在")
    if role.is_builtin:
        raise HTTPException(400, "内置角色不可删除")
    db.query(UserRole).filter(UserRole.role_id == role_id).delete()
    db.query(RoleMenu).filter(RoleMenu.role_id == role_id).delete()
    db.delete(role)
    db.commit()
    return {"ok": True}
