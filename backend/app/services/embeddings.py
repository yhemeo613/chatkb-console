# -*- coding: utf-8 -*-
"""带 Redis 缓存的嵌入服务：相同文本+模型只向量化一次（TTL 7 天）"""
import hashlib

from . import cache, ollama_client

TTL = 7 * 24 * 3600


def _key(model: str, text: str) -> str:
    h = hashlib.sha256(f"{model}:{text}".encode()).hexdigest()
    return f"emb:{model}:{h}"


def embed_texts(texts: list[str], model: str) -> list[list[float] | None]:
    """返回与 texts 等长的向量列表；未命中缓存的文本批量向量化"""
    vectors: list[list[float] | None] = [cache.get_json(_key(model, t)) for t in texts]
    misses = [i for i, v in enumerate(vectors) if v is None]
    if misses:
        fresh = ollama_client.embed([texts[i] for i in misses], model)
        for i, vec in zip(misses, fresh):
            vectors[i] = vec
            cache.set_json(_key(model, texts[i]), vec, ttl=TTL)
    return vectors


def embed_one(text: str, model: str) -> list[float]:
    return embed_texts([text], model)[0]
