# -*- coding: utf-8 -*-
"""文档上传 / 列表 / 删除（SQLAlchemy + JWT）"""
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db, new_id, now
from ..config import UPLOAD_DIR
from ..models import Document
from ..services import ingest, parsing, vectorstore
from ..services.security import get_current_user, require_perm
from .kbs import get_kb_or_404

router = APIRouter(prefix="/api/kbs/{kb_id}/documents", tags=["文档"],
                   dependencies=[Depends(get_current_user)])


@router.get("")
def list_documents(kb_id: str, db: Session = Depends(get_db)):
    get_kb_or_404(kb_id, db)
    docs = db.query(Document).filter(Document.kb_id == kb_id).order_by(Document.created_at.desc())
    return [{c.name: getattr(d, c.name) for c in d.__table__.columns} for d in docs]


@router.post("", dependencies=[Depends(require_perm("kb:upload"))])
async def upload(kb_id: str, files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    get_kb_or_404(kb_id, db)
    dest_dir = Path(UPLOAD_DIR) / kb_id
    dest_dir.mkdir(parents=True, exist_ok=True)

    doc_ids = []
    for f in files:
        if Path(f.filename).suffix.lower() not in parsing.SUPPORTED_EXTS:
            raise HTTPException(400, f"不支持的格式：{f.filename}（支持 pdf/epub/docx/txt/md/html）")
        doc_id = new_id()
        dest = dest_dir / f"{doc_id}_{f.filename}"
        with open(dest, "wb") as out:
            shutil.copyfileobj(f.file, out)
        db.add(Document(id=doc_id, kb_id=kb_id, filename=f.filename, stored_path=str(dest),
                        size=dest.stat().st_size, status="pending", chunks=0, error="",
                        created_at=now(), updated_at=now()))
        doc_ids.append(doc_id)
    db.commit()
    task_id = ingest.submit_ingest(kb_id, doc_ids)
    return {"task_id": task_id, "doc_count": len(doc_ids)}


@router.delete("/{doc_id}", dependencies=[Depends(require_perm("kb:delete"))])
def delete_document(kb_id: str, doc_id: str, db: Session = Depends(get_db)):
    get_kb_or_404(kb_id, db)
    doc = db.query(Document).filter(Document.id == doc_id, Document.kb_id == kb_id).first()
    if not doc:
        raise HTTPException(404, "文档不存在")
    try:
        Path(doc.stored_path).unlink(missing_ok=True)
    except Exception:
        pass
    try:
        vectorstore.collection(kb_id).delete(where={"doc_id": doc_id})
    except Exception:
        pass
    db.delete(doc)
    db.commit()
    return {"ok": True}
