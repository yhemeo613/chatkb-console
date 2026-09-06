# -*- coding: utf-8 -*-
"""pytest 配置：TestClient 夹具 + Ollama mock

关键：先于 app 导入设置独立向量库目录，避免与运行中的后端进程并发写同一 Chroma
导致段文件损坏（Windows 上 chroma rust 后端不支持多进程安全写入）。
"""
import os
import shutil
from pathlib import Path

_TEST_CHROMA = Path(__file__).resolve().parent.parent / "data" / "chroma_test"
if _TEST_CHROMA.exists():
    shutil.rmtree(_TEST_CHROMA, ignore_errors=True)
os.environ["CHATKB_CHROMA_DIR"] = str(_TEST_CHROMA)

import pytest

from app.main import app
from app.services import embeddings, ollama_client


@pytest.fixture(scope="session")
def client():
    with __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth(client):
    res = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def mock_ollama(monkeypatch):
    """全部测试不依赖真实 Ollama：1024 维向量（与 bge-m3 同维，兼容真实库的检索）+ 固定回复"""
    vec = [0.01] * 1024
    monkeypatch.setattr(embeddings, "embed_one", lambda text, model: vec)
    monkeypatch.setattr(
        embeddings, "embed_texts",
        lambda texts, model: [vec for _ in texts],
    )
    monkeypatch.setattr(
        ollama_client, "chat",
        lambda model, system, user, temperature=0.8: "1. 稳妥回复\n2. 幽默回复\n3. 简短回复",
    )
    from app.services import llm as llm_service
    monkeypatch.setattr(
        llm_service, "chat_completion",
        lambda base_url, api_key, model, system, user, temperature=0.8, timeout=600, no_think=False:
            ("1. 稳妥回复\n2. 幽默回复\n3. 简短回复",
             {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30, "latency_ms": 5}),
    )
    monkeypatch.setattr(ollama_client, "is_up", lambda: True)
    monkeypatch.setattr(ollama_client, "list_models", lambda: ["mock-model"])


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    """会话结束清理本进程创建的测试知识库（走 API，避免与后端并发写向量库）"""
    import requests as _rq
    try:
        B = "http://127.0.0.1:8000"
        tok = _rq.post(f"{B}/api/auth/login",
                       json={"username": "admin", "password": "admin123"}, timeout=5).json()["access_token"]
        H = {"Authorization": f"Bearer {tok}"}
        for k in _rq.get(f"{B}/api/kbs", headers=H, timeout=5).json():
            if "测试" in k["name"] or "权限测试" in k["name"]:
                _rq.delete(f"{B}/api/kbs/{k['id']}", headers=H, timeout=10)
    except Exception:
        pass  # 后端未运行时跳过，残留可在界面删除
