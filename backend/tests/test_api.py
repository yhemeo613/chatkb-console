# -*- coding: utf-8 -*-
"""API 回归测试（不依赖 Ollama，见 conftest 的 mock）"""
import time

import pytest


def _wait_task(client, auth, task_id, timeout=60):
    for _ in range(timeout):
        t = client.get(f"/api/system/tasks/{task_id}", headers=auth).json()
        if t.get("status") != "running":
            return t
        time.sleep(0.3)
    raise TimeoutError(f"任务超时: {task_id}")


# ---------- 认证 ----------

def test_login_rejects_wrong_password(client):
    res = client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
    assert res.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_login_and_me(client, auth):
    res = client.get("/api/auth/me", headers=auth)
    assert res.status_code == 200
    assert res.json()["username"] == "admin"


def test_change_password(client, auth):
    assert client.post("/api/auth/change-password", headers=auth,
                       json={"old_password": "admin123", "new_password": "admin123"}).status_code == 200


# ---------- 知识库 ----------

def test_kb_crud(client, auth):
    kb_id = client.post("/api/kbs", headers=auth,
                        json={"name": "测试库", "type": "docs"}).json()["id"]
    kbs = client.get("/api/kbs", headers=auth).json()
    assert any(k["id"] == kb_id and k["name"] == "测试库" for k in kbs)

    assert client.put(f"/api/kbs/{kb_id}", headers=auth,
                      json={"description": "测试描述"}).status_code == 200
    assert client.get(f"/api/kbs/{kb_id}", headers=auth).json()["description"] == "测试描述"
    assert client.delete(f"/api/kbs/{kb_id}", headers=auth).json()["ok"]
    assert client.get(f"/api/kbs/{kb_id}", headers=auth).status_code == 404


# ---------- 文档入库 + 搜索 + 回复 ----------

@pytest.fixture(scope="module")
def doc_kb(client, auth):
    return client.post("/api/kbs", headers=auth, json={"name": "测试文档库", "type": "docs"}).json()["id"]


def test_upload_ingest_search_reply(client, auth, doc_kb):
    files = {"files": ("话术.md", "拒绝别人时使用三明治法，先肯定再拒绝再给台阶。".encode(), "text/markdown")}
    res = client.post(f"/api/kbs/{doc_kb}/documents", headers=auth, files=files)
    assert res.status_code == 200
    task = _wait_task(client, auth, res.json()["task_id"])
    assert task["status"] == "success", task

    docs = client.get(f"/api/kbs/{doc_kb}/documents", headers=auth).json()
    assert docs[0]["status"] == "done" and docs[0]["chunks"] >= 1

    hits = client.post("/api/search", headers=auth,
                       json={"query": "如何拒绝别人", "kb_ids": [doc_kb]}).json()
    assert len(hits["hits"]) >= 1
    assert "三明治" in hits["hits"][0]["text"]

    reply = client.post("/api/chat/reply", headers=auth,
                        json={"message": "周末有空吗"}).json()
    assert len(reply["candidates"]) == 3


def test_delete_document(client, auth, doc_kb):
    docs = client.get(f"/api/kbs/{doc_kb}/documents", headers=auth).json()
    assert client.delete(f"/api/kbs/{doc_kb}/documents/{docs[0]['id']}",
                         headers=auth).json()["ok"]


# ---------- 个人档案 / 设置 ----------

def test_profiles_crud(client, auth):
    name = "99_测试档案"
    assert client.post("/api/profiles", headers=auth,
                       json={"name": name, "person": "测试对象"}).status_code == 200
    assert name + ".md" in [p["name"] for p in client.get("/api/profiles", headers=auth).json()]

    res = client.put(f"/api/profiles/{name}", headers=auth,
                     json={"content": "---\nperson: 测试对象\n---\n\n更新内容"})
    assert res.status_code == 200
    assert "更新内容" in client.get(f"/api/profiles/{name}", headers=auth).json()["content"]

    assert client.delete(f"/api/profiles/{name}", headers=auth).json()["ok"]


def test_settings_roundtrip(client, auth):
    cur = client.get("/api/system/settings", headers=auth).json()
    res = client.put("/api/system/settings", headers=auth, json={"top_k": cur["top_k"]})
    assert res.status_code == 200
    assert "jwt_secret" not in client.get("/api/system/settings", headers=auth).json()


def test_dashboard(client, auth):
    d = client.get("/api/system/dashboard", headers=auth).json()
    assert d["kb_count"] >= 2
    assert d["redis_backend"] in ("redis", "fakeredis")
