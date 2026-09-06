# -*- coding: utf-8 -*-
"""运维监控：服务健康 / 任务中心 / 操作日志"""
import os
import time

import requests as http_client
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import database as _db
from ..config import CHROMA_DIR, DATA_DIR, DB_PATH, OLLAMA_URL, REDIS_URL, load_settings
from ..database import get_db
from ..models import AuditLog, Document
from ..services import cache, ollama_client, tasks
from ..services.security import get_current_user, require_perm

router = APIRouter(prefix="/api/ops", tags=["运维监控"])
STARTED_AT = time.time()


def _dir_size(path) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


@router.get("/status", dependencies=[Depends(require_perm("ops:status"))])
def status(db: Session = Depends(get_db)):
    # Ollama
    ollama_up = ollama_client.is_up()
    ollama_version = ""
    if ollama_up:
        try:
            ollama_version = http_client.get(f"{OLLAMA_URL}/api/version", timeout=3).json().get("version", "")
        except Exception:
            pass

    # Redis
    redis_ok = True
    redis_info = {}
    try:
        c = cache.get_client()
        info = c.info("memory") if cache.backend_name() == "redis" else {}
        redis_info = {
            "used_memory_human": info.get("used_memory_human", "-"),
            "keys": sum(1 for _ in c.scan_iter("chatkb:*", count=500)),
        }
    except Exception:
        redis_ok = False

    settings = load_settings()
    return {
        "uptime_sec": round(time.time() - STARTED_AT),
        "python": os.sys.version.split()[0],
        "ollama": {"up": ollama_up, "version": ollama_version,
                   "models": ollama_client.list_models(), "url": OLLAMA_URL},
        "redis": {"up": redis_ok, "backend": cache.backend_name(), "url": REDIS_URL, **redis_info},
        "sqlite": {"path": str(DB_PATH), "size": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
                   "docs": db.query(Document).count(),
                   "audit": db.scalar(select(func.count(AuditLog.id))) or 0},
        "chroma": {"path": str(CHROMA_DIR), "size": _dir_size(CHROMA_DIR)},
        "settings": {"chat_model": settings["chat_model"], "embed_model": settings["embed_model"],
                     "rate_limit_per_min": settings["rate_limit_per_min"]},
        "task_running": tasks.running_count(),
    }


@router.get("/tasks", dependencies=[Depends(require_perm("ops:tasks"))])
def recent_tasks(limit: int = 50):
    return tasks.recent(limit)


@router.get("/logs", dependencies=[Depends(require_perm("ops:logs"))])
def audit_logs(page: int = 1, size: int = 20, db: Session = Depends(get_db)):
    total = db.scalar(select(func.count(AuditLog.id))) or 0
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc())
                      .offset((page - 1) * size).limit(size)).all()
    return {"total": total, "items": [{
        "id": r.id, "username": r.username, "method": r.method, "path": r.path,
        "status_code": r.status_code, "ip": r.ip, "duration_ms": r.duration_ms,
        "created_at": r.created_at} for r in rows]}
