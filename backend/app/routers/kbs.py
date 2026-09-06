# -*- coding: utf-8 -*-
"""知识库 CRUD + 重建索引（SQLAlchemy + JWT 保护）"""
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..config import UPLOAD_DIR, load_settings
from ..database import SessionLocal, get_db, new_id, now
from ..models import Document, KnowledgeBase
from ..services import embeddings, ingest, tasks, vectorstore
from ..services.security import get_current_user, require_perm

router = APIRouter(prefix="/api/kbs", tags=["知识库"], dependencies=[Depends(get_current_user)])


def get_kb_or_404(kb_id: str, db: Session) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(404, "知识库不存在")
    return kb


@router.get("")
def list_kbs(db: Session = Depends(get_db)):
    from sqlalchemy import func
    out = []
    for kb in db.scalars(select(KnowledgeBase).order_by(KnowledgeBase.created_at)):
        d = {c.name: getattr(kb, c.name) for c in kb.__table__.columns}
        out.append(d)
    counts = dict(db.execute(
        select(Document.kb_id, func.count(Document.id)).group_by(Document.kb_id)).all())
    for d in out:
        d["doc_count"] = counts.get(d["id"], 0)
        d["chunk_count"] = vectorstore.collection(d["id"]).count()
    return out


@router.post("", dependencies=[Depends(require_perm("kb:create"))])
def create_kb(body: schemas.KbCreate, db: Session = Depends(get_db)):
    if body.type not in ("docs", "persona"):
        raise HTTPException(400, "类型必须是 docs 或 persona")
    s = load_settings()
    kb = KnowledgeBase(
        id=new_id(), name=body.name.strip(), description=body.description.strip(),
        type=body.type, embed_model=body.embed_model or s["embed_model"],
        chunk_size=body.chunk_size or s["chunk_size"],
        chunk_overlap=body.chunk_overlap or s["chunk_overlap"], created_at=now(),
    )
    db.add(kb)
    db.commit()
    return {"id": kb.id}


@router.get("/{kb_id}")
def get_kb(kb_id: str, db: Session = Depends(get_db)):
    kb = get_kb_or_404(kb_id, db)
    return {c.name: getattr(kb, c.name) for c in kb.__table__.columns}


@router.put("/{kb_id}")
def update_kb(kb_id: str, body: schemas.KbUpdate, db: Session = Depends(get_db)):
    kb = get_kb_or_404(kb_id, db)
    if body.name is not None:
        kb.name = body.name.strip()
    if body.description is not None:
        kb.description = body.description.strip()
    db.commit()
    return {"ok": True}


@router.delete("/{kb_id}", dependencies=[Depends(require_perm("kb:delete"))])
def delete_kb(kb_id: str, db: Session = Depends(get_db)):
    get_kb_or_404(kb_id, db)
    shutil.rmtree(Path(UPLOAD_DIR) / kb_id, ignore_errors=True)
    db.query(Document).filter(Document.kb_id == kb_id).delete()
    db.get(KnowledgeBase, kb_id) and db.delete(db.get(KnowledgeBase, kb_id))
    db.commit()
    vectorstore.drop_collection(kb_id)
    return {"ok": True}


@router.post("/{kb_id}/rebuild", dependencies=[Depends(require_perm("kb:rebuild"))])
def rebuild(kb_id: str, db: Session = Depends(get_db)):
    kb = get_kb_or_404(kb_id, db)
    if kb.type == "persona":
        task_id = ingest.submit_persona_sync(kb_id)
    else:
        task_id = ingest.submit_rebuild(kb_id)
    return {"task_id": task_id}


# 供 chat / search 复用的查询函数
def all_kbs(db: Session) -> list[KnowledgeBase]:
    return list(db.scalars(select(KnowledgeBase)))
