# -*- coding: utf-8 -*-
"""Chroma 向量库封装：每个知识库一个 collection"""
import chromadb

from ..config import CHROMA_DIR

_client = None


def client() -> chromadb.api.ClientAPI:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _client


def collection(kb_id: str):
    return client().get_or_create_collection(f"kb_{kb_id}", metadata={"hnsw:space": "cosine"})


def drop_collection(kb_id: str):
    try:
        client().delete_collection(f"kb_{kb_id}")
    except Exception:
        pass


def query(kb_id: str, embedding: list[float], top_k: int, where: dict | None = None):
    col = collection(kb_id)
    if col.count() == 0:
        return []
    res = col.query(
        query_embeddings=[embedding],
        n_results=min(top_k, col.count()),
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    hits = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        hits.append({"text": doc, "metadata": meta, "score": round(1 - dist, 4)})
    return hits
