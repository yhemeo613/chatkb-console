# -*- coding: utf-8 -*-
"""系统：仪表盘 / 模型 / 设置 / 任务（含 Redis 状态）"""
from fastapi import APIRouter, Depends, HTTPException

from .. import schemas
from ..config import load_settings, save_settings
from ..database import get_db, now
from ..models import Document
from ..services import cache, ollama_client, tasks
from ..services.security import get_current_user

router = APIRouter(prefix="/api/system", tags=["系统"], dependencies=[Depends(get_current_user)])


@router.get("/dashboard")
def dashboard(db=Depends(get_db)):
    doc_total = db.query(Document).count()
    doc_done = db.query(Document).filter(Document.status == "done").count()
    doc_failed = db.query(Document).filter(Document.status == "failed").count()
    recent = db.query(Document).order_by(Document.created_at.desc()).limit(8)
    from ..models import KnowledgeBase
    kb_names = {k.id: k.name for k in db.query(KnowledgeBase)}
    chunk_total = sum(d.chunks or 0 for d in db.query(Document))
    s = load_settings()
    return {
        "kb_count": len(kb_names),
        "doc_total": doc_total,
        "doc_done": doc_done,
        "doc_failed": doc_failed,
        "chunk_total": chunk_total,
        "recent_docs": [{**{c.name: getattr(d, c.name) for c in d.__table__.columns},
                         "kb_name": kb_names.get(d.kb_id, "")} for d in recent],
        "ollama_up": ollama_client.is_up(),
        "models": ollama_client.list_models(),
        "task_running": tasks.running_count(),
        "redis_backend": cache.backend_name(),
        "chat_model": s["chat_model"],
    }


@router.get("/models")
def models():
    return {"models": ollama_client.list_models(), "ollama_up": ollama_client.is_up()}


@router.get("/settings")
def get_settings():
    s = load_settings()
    return {k: v for k, v in s.items() if k != "jwt_secret"}  # 密钥不下发


@router.put("/settings")
def put_settings(body: dict):
    body.pop("jwt_secret", None)
    return {k: v for k, v in save_settings(body).items() if k != "jwt_secret"}


@router.get("/tasks/{task_id}")
def task_detail(task_id: str):
    t = tasks.get(task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    return t
