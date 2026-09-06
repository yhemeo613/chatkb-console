# -*- coding: utf-8 -*-
"""个人档案：markdown 在线编辑，保存后自动同步个人档案知识库"""
import re

from fastapi import APIRouter, Depends, HTTPException

from .. import schemas
from ..config import PERSONA_DIR
from ..database import get_db
from ..services import ingest, parsing
from ..services.security import require_perm

router = APIRouter(prefix="/api/profiles", tags=["个人档案"], dependencies=[Depends(require_perm("profile"))])


def _safe_name(name: str) -> str:
    name = name.strip()
    if not re.fullmatch(r"[\w\u4e00-\u9fff\- ]+\.md", name + (".md" if not name.endswith(".md") else "")) or ".." in name:
        raise HTTPException(400, "文件名只能包含中文、字母、数字、下划线、连字符")
    return name if name.endswith(".md") else name + ".md"


def _persona_kb_id(db) -> str | None:
    from ..models import KnowledgeBase
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.type == "persona").first()
    return kb.id if kb else None


@router.get("")
def list_profiles():
    out = []
    for f in sorted(PERSONA_DIR.glob("*.md")):
        meta, _ = parsing.parse_frontmatter(f.read_text(encoding="utf-8", errors="ignore"))
        st = f.stat()
        out.append({"name": f.name, "person": meta.get("person", ""),
                    "size": st.st_size, "updated_at": st.st_mtime})
    return out


@router.get("/persons")
def persons():
    return sorted({p["person"] for p in list_profiles() if p["person"]})


@router.get("/{name}")
def get_profile(name: str):
    path = PERSONA_DIR / _safe_name(name)
    if not path.exists():
        raise HTTPException(404, "档案不存在")
    return {"name": path.name, "content": path.read_text(encoding="utf-8", errors="ignore")}


@router.post("", dependencies=[Depends(require_perm("profile:manage"))])
def create_profile(body: schemas.ProfileCreate, db=Depends(get_db)):
    name = _safe_name(body.name)
    path = PERSONA_DIR / name
    if path.exists():
        raise HTTPException(400, "同名档案已存在")
    content = body.content or f"---\nperson: {body.person}\n---\n\n# {body.person or name}\n"
    path.write_text(content, encoding="utf-8")
    kb_id = _persona_kb_id(db)
    if kb_id:
        ingest.submit_persona_sync(kb_id)
    return {"name": name}


@router.put("/{name}", dependencies=[Depends(require_perm("profile:manage"))])
def update_profile(name: str, body: schemas.ProfileUpdate, db=Depends(get_db)):
    path = PERSONA_DIR / _safe_name(name)
    if not path.exists():
        raise HTTPException(404, "档案不存在")
    path.write_text(body.content, encoding="utf-8")
    kb_id = _persona_kb_id(db)
    if kb_id:
        ingest.submit_persona_sync(kb_id)
    return {"ok": True}


@router.delete("/{name}", dependencies=[Depends(require_perm("profile:manage"))])
def delete_profile(name: str, db=Depends(get_db)):
    path = PERSONA_DIR / _safe_name(name)
    if not path.exists():
        raise HTTPException(404, "档案不存在")
    path.unlink()
    kb_id = _persona_kb_id(db)
    if kb_id:
        ingest.submit_persona_sync(kb_id)
    return {"ok": True}
