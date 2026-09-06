# -*- coding: utf-8 -*-
"""安全：PBKDF2 口令散列 + JWT + 当前用户依赖 + RBAC 权限校验器"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import load_settings
from ..models import Menu, Role, RoleMenu, User, UserRole

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return secrets.compare_digest(hash_password(password, salt), stored)


def create_access_token(user_id: str, username: str) -> str:
    s = load_settings()
    payload = {
        "sub": user_id,
        "username": username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=int(s["token_expire_hours"])),
    }
    return jwt.encode(payload, s["jwt_secret"], algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, load_settings()["jwt_secret"], algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def _menu_dict(m: Menu) -> dict:
    return {"id": m.id, "parentId": m.parent_id or "", "name": m.name, "type": m.type,
            "path": m.path, "icon": m.icon, "permCode": m.perm_code,
            "sort": m.sort or 0, "visible": m.visible}


def build_menu_tree(flat: list[dict]) -> list[dict]:
    """扁平菜单 -> 树（按钮节点不进侧边栏树，仅作为权限码）"""
    nodes = {m["id"]: {**m, "children": []} for m in flat}
    roots = []
    for node in nodes.values():
        parent = nodes.get(node["parentId"])
        if parent:
            parent["children"].append(node)
        else:
            roots.append(node)

    def clean(items):
        out = []
        for n in sorted(items, key=lambda x: (x["sort"], x["name"])):
            n["children"] = clean(n["children"])
            if n["type"] != "button":
                out.append(n)
        return out

    return clean(roots)


def load_user_access(db: Session, user: User) -> dict:
    """装配用户的角色、权限码、可见菜单树"""
    roles = db.scalars(select(Role).join(UserRole, UserRole.role_id == Role.id)
                       .where(UserRole.user_id == user.id)).all()
    role_list = [{"id": r.id, "code": r.code, "name": r.name} for r in roles]

    all_menus = list(db.scalars(select(Menu).order_by(Menu.sort)))
    if user.is_superuser:
        granted = all_menus
    else:
        role_ids = [r.id for r in roles]
        granted = list(db.scalars(
            select(Menu).join(RoleMenu, RoleMenu.menu_id == Menu.id)
            .where(RoleMenu.role_id.in_(role_ids)))) if role_ids else []

    perms = sorted({m.perm_code for m in granted if m.perm_code})

    # 补齐被授权节点的祖先目录，保证菜单树连通
    if user.is_superuser or len(granted) == len(all_menus):
        visible = {m.id: m for m in all_menus}
    else:
        by_id = {m.id: m for m in all_menus}
        visible = {}
        for m in granted:
            visible[m.id] = m
            pid = m.parent_id
            while pid and pid not in visible:
                parent = by_id.get(pid)
                if not parent:
                    break
                visible[pid] = parent
                pid = parent.parent_id

    return {
        "roles": role_list,
        "perms": perms,
        "menus": build_menu_tree([_menu_dict(m) for m in visible.values()]),
    }


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if credentials is None:
        import logging
        logging.getLogger("chatkb.auth").warning("401: 请求无 Authorization 头")
        raise HTTPException(401, "未登录")
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(401, "登录已过期，请重新登录")
    return {"id": payload["sub"], "username": payload["username"]}


def load_active_user(db: Session, user_id: str) -> User | None:
    user = db.get(User, user_id)
    if not user or user.status != "active":
        return None
    return user


def require_perm(perm: str):
    """RBAC 鉴权依赖工厂：超管直通，否则要求持有指定权限码"""
    def dep(user: dict = Depends(get_current_user)):
        from ..database import SessionLocal
        db = SessionLocal()
        try:
            full = load_active_user(db, user["id"])
            if not full:
                raise HTTPException(401, "账号已被禁用或删除")
            if full.is_superuser:
                return user
            if perm not in load_user_access(db, full)["perms"]:
                raise HTTPException(403, f"缺少权限：{perm}")
            return user
        finally:
            db.close()
    return dep


def user_from_token(token: str) -> dict | None:
    """供 WebSocket（token 走查询参数）使用"""
    payload = decode_token(token)
    return {"id": payload["sub"], "username": payload["username"]} if payload else None
