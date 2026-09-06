# -*- coding: utf-8 -*-
"""Redis 可视化：键扫描 / 值查看 / TTL / 删除"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..services import cache
from ..services.security import require_perm

router = APIRouter(prefix="/api/ext/redis", tags=["Redis管理"],
                   dependencies=[Depends(require_perm("ext:redis"))])


@router.get("/keys")
def list_keys(pattern: str = "chatkb:*", limit: int = 200):
    c = cache.get_client()
    out = []
    for k in c.scan_iter(match=pattern, count=200):
        if len(out) >= limit:
            break
        t = c.type(k)
        out.append({
            "key": k, "type": t,
            "size": len(c.get(k) or "") if t == "string" else int(c.memory_usage(k) or 0),
            "ttl": c.ttl(k),
        })
    return {"total": len(out), "items": out, "backend": cache.backend_name()}


@router.get("/key")
def get_key(key: str):
    c = cache.get_client()
    if not c.exists(key):
        raise HTTPException(404, "键不存在")
    t = c.type(key)
    if t == "string":
        raw = c.get(key) or ""
        try:
            value = json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
            kind = "json"
        except Exception:
            value, kind = raw, "text"
        return {"key": key, "type": t, "ttl": c.ttl(key), "kind": kind, "value": value[:20000]}
    if t == "hash":
        return {"key": key, "type": t, "ttl": c.ttl(key), "kind": "hash", "value": c.hgetall(key)}
    return {"key": key, "type": t, "ttl": c.ttl(key), "kind": t, "value": str(c.smembers(key) or c.lrange(key, 0, -1))}


class DeleteIn(BaseModel):
    keys: list[str]


@router.post("/delete")
def delete_keys(body: DeleteIn):
    c = cache.get_client()
    n = 0
    for k in body.keys:
        if k.startswith(cache.PREFIX):
            n += int(c.delete(k))
    return {"deleted": n}


@router.post("/key/ttl")
def set_ttl(body: dict):
    c = cache.get_client()
    key = body.get("key", "")
    ttl = int(body.get("ttl", -1))
    if not key.startswith(cache.PREFIX):
        raise HTTPException(400, "仅允许操作 chatkb: 前缀的键")
    if ttl < 0:
        c.persist(key)
    else:
        c.expire(key, ttl)
    return {"ok": True, "ttl": c.ttl(key)}
