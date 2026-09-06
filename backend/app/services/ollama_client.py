# -*- coding: utf-8 -*-
"""Ollama HTTP 客户端：嵌入、对话、模型列表"""
import time

import requests

from ..config import OLLAMA_URL

EMBED_BATCH = 32
_tags_cache = {"at": 0.0, "up": False, "models": []}
TAGS_TTL = 10  # 秒；本机 Ollama /api/tags 响应较慢，短缓存供状态栏/仪表盘复用


def _fetch_tags():
    now = time.time()
    if now - _tags_cache["at"] < TAGS_TTL:
        return _tags_cache["up"], _tags_cache["models"]
    up, models = False, []
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        up = True
    except Exception:
        pass
    _tags_cache.update(at=now, up=up, models=models)
    return up, models


def is_up() -> bool:
    return _fetch_tags()[0]


def list_models() -> list[str]:
    return _fetch_tags()[1]


def embed(texts: list[str], model: str) -> list[list[float]]:
    out = []
    for i in range(0, len(texts), EMBED_BATCH):
        r = requests.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": model, "input": texts[i:i + EMBED_BATCH]},
            timeout=600,
        )
        r.raise_for_status()
        out.extend(r.json()["embeddings"])
    return out


def embed_one(text: str, model: str) -> list[float]:
    return embed([text], model)[0]


def chat(model: str, system: str, user: str, temperature: float = 0.8) -> str:
    r = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user + "\n/no_think"},
            ],
            "stream": False,
            "options": {"temperature": temperature},
        },
        timeout=600,
    )
    r.raise_for_status()
    return r.json()["message"]["content"]
