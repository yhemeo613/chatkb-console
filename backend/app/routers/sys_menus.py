# -*- coding: utf-8 -*-
"""菜单管理：三级菜单树 CRUD（目录/菜单/按钮）"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db, new_id, now
from ..models import Menu, RoleMenu
from ..services.security import require_perm

router = APIRouter(prefix="/api/system/menus", tags=["菜单管理"],
                   dependencies=[Depends(require_perm("sys:menu"))])

VALID_TYPES = ("dir", "menu", "button")


class MenuIn(BaseModel):
    parent_id: str = ""
    name: str = Field(min_length=1, max_length=64)
    type: str
    path: str = ""
    icon: str = ""
    perm_code: str = ""
    sort: int = 0
    visible: int = 1


def _tree(rows: list[Menu]) -> list[dict]:
    nodes = {}
    for m in sorted(rows, key=lambda x: (x.sort or 0, x.name)):
        nodes[m.id] = {"id": m.id, "parentId": m.parent_id or "", "name": m.name,
                       "type": m.type, "path": m.path, "icon": m.icon,
                       "permCode": m.perm_code, "sort": m.sort, "visible": m.visible,
                       "createdAt": m.created_at, "children": []}
    roots = []
    for node in nodes.values():
        parent = nodes.get(node["parentId"])
        (parent["children"] if parent else roots).append(node)
    return roots


@router.get("")
def menu_tree(db: Session = Depends(get_db)):
    rows = list(db.scalars(select(Menu).order_by(Menu.sort)))
    return _tree(rows)


def _flat(db: Session) -> list[Menu]:
    return list(db.scalars(select(Menu).order_by(Menu.sort)))


@router.post("", dependencies=[Depends(require_perm("sys:menu:create"))])
def create_menu(body: MenuIn, db: Session = Depends(get_db)):
    if body.type not in VALID_TYPES:
        raise HTTPException(400, "类型必须是 dir/menu/button")
    if body.parent_id and not db.get(Menu, body.parent_id):
        raise HTTPException(400, "父级菜单不存在")
    m = Menu(id=new_id(), parent_id=body.parent_id or None, name=body.name.strip(),
             type=body.type, path=body.path.strip(), icon=body.icon.strip(),
             perm_code=body.perm_code.strip(), sort=body.sort, visible=body.visible,
             created_at=now())
    db.add(m)
    db.commit()
    return {"id": m.id}


@router.put("/{menu_id}", dependencies=[Depends(require_perm("sys:menu:update"))])
def update_menu(menu_id: str, body: MenuIn, db: Session = Depends(get_db)):
    m = db.get(Menu, menu_id)
    if not m:
        raise HTTPException(404, "菜单不存在")
    if body.type not in VALID_TYPES:
        raise HTTPException(400, "类型必须是 dir/menu/button")
    if body.parent_id == menu_id:
        raise HTTPException(400, "不能把自己设为父级")
    # 防止把父级挪到自己的子树里形成环
    flat = {x.id: x for x in _flat(db)}
    pid, guard = body.parent_id or "", 0
    while pid and guard < 10:
        if pid == menu_id:
            raise HTTPException(400, "不能把父级设为自己的子孙节点")
        parent = flat.get(pid)
        pid = parent.parent_id if parent else ""
        guard += 1
    m.parent_id = body.parent_id or None
    m.name, m.type = body.name.strip(), body.type
    m.path, m.icon = body.path.strip(), body.icon.strip()
    m.perm_code, m.sort, m.visible = body.perm_code.strip(), body.sort, body.visible
    db.commit()
    return {"ok": True}


@router.delete("/{menu_id}", dependencies=[Depends(require_perm("sys:menu:delete"))])
def delete_menu(menu_id: str, db: Session = Depends(get_db)):
    m = db.get(Menu, menu_id)
    if not m:
        raise HTTPException(404, "菜单不存在")
    if any(x.parent_id == menu_id for x in _flat(db)):
        raise HTTPException(400, "请先删除子级菜单")
    db.query(RoleMenu).filter(RoleMenu.menu_id == menu_id).delete()
    db.delete(m)
    db.commit()
    return {"ok": True}
