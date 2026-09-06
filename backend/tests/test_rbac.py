# -*- coding: utf-8 -*-
"""RBAC / 注册 / 菜单权限 回归测试"""
import uuid


def _uname() -> str:
    return "u" + uuid.uuid4().hex[:8]


def test_register_default_role(client):
    uname = _uname()
    res = client.post("/api/auth/register", json={
        "username": uname, "password": "pass123", "nickname": "测试用户"})
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    user = res.json()["user"]

    # 普通用户角色 + 受限菜单
    assert [r["code"] for r in user["roles"]] == ["user"]
    menu_paths = _flatten_paths(user["menus"])
    assert "/dashboard" in menu_paths and "/search" in menu_paths and "/reply" in menu_paths
    assert "/system/users" not in menu_paths and "/ops/status" not in menu_paths

    # 拿着普通用户 token：能搜索，不能进账号管理，也不能建知识库
    H = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=H).status_code == 200
    assert client.get("/api/system/users", headers=H).status_code == 403
    assert client.post("/api/kbs", headers=H, json={"name": "x"}).status_code == 403


def test_admin_manages_users_and_roles(client, auth):
    uname = _uname()
    roles = {r["code"]: r["id"] for r in client.get("/api/system/roles", headers=auth).json()}
    assert {"super_admin", "kb_admin", "user", "ops"} <= set(roles)

    # 建一个知识管理员
    created = client.post("/api/system/users", headers=auth, json={
        "username": uname, "password": "pass123", "nickname": "知识管理员",
        "role_ids": [roles["kb_admin"]]}).json()
    assert created["status"] == "active"

    # 该用户能建知识库（kb:create），但进不了账号管理（sys:user）
    tok = client.post("/api/auth/login", json={"username": uname, "password": "pass123"}).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/system/users", headers=H).status_code == 403
    kb_id = client.post("/api/kbs", headers=H, json={"name": "权限测试库"}).json()["id"]
    assert kb_id

    # 禁用后立即无法登录
    assert client.put(f"/api/system/users/{created['id']}", headers=auth,
                      json={"status": "disabled"}).status_code == 200
    assert client.post("/api/auth/login", json={"username": uname, "password": "pass123"}).status_code == 403

    # 重置密码 → 恢复启用 → 新密码可登录
    assert client.put(f"/api/system/users/{created['id']}/reset-password", headers=auth,
                      json={"new_password": "newpass456"}).status_code == 200
    assert client.put(f"/api/system/users/{created['id']}", headers=auth,
                      json={"status": "active"}).status_code == 200
    assert client.post("/api/auth/login",
                       json={"username": uname, "password": "newpass456"}).status_code == 200

    # 清理
    assert client.delete(f"/api/kbs/{kb_id}", headers=auth).json()["ok"]
    assert client.delete(f"/api/system/users/{created['id']}", headers=auth).json()["ok"]


def test_menu_tree_two_levels(client, auth):
    """系统管理为二级结构：账号/角色/菜单管理直接挂在其下（用户要求去掉权限管理层）"""
    tree = client.get("/api/system/menus", headers=auth).json()
    names = [n["name"] for n in tree]
    assert "系统管理" in names and "运维监控" in names and "模型中心" in names

    sys_node = next(n for n in tree if n["name"] == "系统管理")
    child_names = [c["name"] for c in sys_node["children"]]
    assert {"账号管理", "角色管理", "菜单管理"} <= set(child_names)
    assert all(c["type"] != "dir" for c in sys_node["children"])  # 系统管理下不再有目录层
    # 按钮节点挂在菜单下，携带权限码
    user_menu = next(c for c in sys_node["children"] if c["name"] == "账号管理")
    assert "sys:user:create" in [b["permCode"] for b in user_menu["children"]]


def test_role_crud_with_menu_grant(client, auth):
    tree = client.get("/api/system/menus", headers=auth).json()
    flat = {}

    def walk(nodes):
        for n in nodes:
            flat[n["name"]] = n["id"]
            walk(n["children"])
    walk(tree)

    role_id = client.post("/api/system/roles", headers=auth, json={
        "name": "临时角色", "code": "tmp_" + uuid.uuid4().hex[:6],
        "description": "测试", "menu_ids": [flat["工作台"], flat["语义搜索"]]}).json()["id"]

    roles = {r["name"]: r for r in client.get("/api/system/roles", headers=auth).json()}
    assert set(roles["临时角色"]["menu_ids"]) == {flat["工作台"], flat["语义搜索"]}

    assert client.delete(f"/api/system/roles/{role_id}", headers=auth).json()["ok"]


def test_audit_log_records_mutations(client, auth):
    uname = _uname()
    client.post("/api/auth/register", json={"username": uname, "password": "pass123"})
    logs = client.get("/api/ops/logs", headers=auth, params={"size": 50}).json()
    paths = [i["path"] for i in logs["items"]]
    assert "/api/auth/register" in paths


def _flatten_paths(nodes, out=None):
    out = out if out is not None else []
    for n in nodes:
        if n.get("path"):
            out.append(n["path"])
        out = _flatten_paths(n.get("children", []), out)
    return out
