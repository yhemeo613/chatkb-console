# -*- coding: utf-8 -*-
"""语义检索：跨知识库 + Redis 结果缓存 + JWT"""
import hashlib

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..config import load_settings
from ..database import get_db
from ..services import cache, embeddings, vectorstore
from ..services.security import get_current_user

router = APIRouter(prefix="/api/search", tags=["检索"], dependencies=[Depends(get_current_user)])


def _cache_key(body: schemas.SearchIn) -> str:
    raw = f"{body.query}|{','.join(sorted(body.kb_ids))}|{body.top_k}"
    return "search:" + hashlib.sha256(raw.encode()).hexdigest()


@router.post("")
def search(body: schemas.SearchIn, db: Session = Depends(get_db)):
    key = _cache_key(body)
    cached = cache.get_json(key)
    if cached is not None:
        return {**cached, "cached": True}

    settings = load_settings()
    top_k = body.top_k or settings["top_k"]

    from ..models import KnowledgeBase
    if body.kb_ids:
        kbs = [db.get(KnowledgeBase, i) for i in body.kb_ids]
        kbs = [k for k in kbs if k]
    else:
        kbs = list(db.query(KnowledgeBase))

    hits = []
    # 不同知识库可能用不同嵌入模型，按模型分组各查各的
    by_model: dict[str, list] = {}
    for kb in kbs:
        by_model.setdefault(kb.embed_model, []).append(kb)
    for model, group in by_model.items():
        emb = embeddings.embed_one(body.query, model)
        for kb in group:
            for h in vectorstore.query(kb.id, emb, top_k):
                h["kb_id"] = kb.id
                h["kb_name"] = kb.name
                h["kb_type"] = kb.type
                hits.append(h)

    hits.sort(key=lambda x: x["score"], reverse=True)
    result = {"hits": hits[: top_k * 2]}
    cache.set_json(key, result, ttl=3600)
    return {**result, "cached": False}
