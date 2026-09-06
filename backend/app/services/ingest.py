# -*- coding: utf-8 -*-
"""入库流水线：文档 -> 解析 -> 分块 -> 嵌入(Redis 缓存) -> Chroma

设计说明：任务在工作线程中执行，每次执行体都重新打开数据库会话，
绝不跨线程复用 ORM 对象。
"""
from pathlib import Path
from time import time

from sqlalchemy import select

from ..config import PERSONA_DIR, load_settings
from ..database import SessionLocal, new_id
from ..models import Document, KnowledgeBase
from ..services import cache, embeddings, parsing, tasks, vectorstore


def _flush_search_cache():
    """知识库内容变化后失效搜索结果缓存"""
    cache.delete_pattern("search:*")


def _ingest_document(db, kb: KnowledgeBase, doc: Document, cb):
    def set_status(status: str, **fields):
        doc.status = status
        for k, v in fields.items():
            setattr(doc, k, v)
        doc.updated_at = time()
        db.commit()

    try:
        set_status("processing")
        path = Path(doc.stored_path)
        if not path.exists():
            raise FileNotFoundError(f"文件丢失：{path}")

        cb(0, f"解析 {doc.filename}")
        if kb.type == "persona":
            _, body = parsing.parse_frontmatter(path.read_text(encoding="utf-8", errors="ignore"))
            sections = [(body, None, None)] if body.strip() else []
        else:
            sections = parsing.extract(path)
        chunks = parsing.make_chunks(sections, kb.chunk_size, kb.chunk_overlap)
        if not chunks:
            raise ValueError("没有可提取的文本")

        cb(0, f"生成向量（{len(chunks)} 块，带缓存）")
        embeddings_list = embeddings.embed_texts([c["text"] for c in chunks], kb.embed_model)

        vectorstore.collection(kb.id).upsert(
            ids=[f"{doc.id}:{i}" for i in range(len(chunks))],
            embeddings=embeddings_list,
            documents=[c["text"] for c in chunks],
            metadatas=[{
                "doc_id": doc.id, "kb_id": kb.id, "source": doc.filename,
                "chapter": c["chapter"], "page": c["page"], "kind": kb.type,
            } for c in chunks],
        )
        set_status("done", chunks=len(chunks), error="")
        cb(1, f"完成 {doc.filename}（{len(chunks)} 块）")
    except Exception as e:
        set_status("failed", error=str(e))
        cb(1, f"失败 {doc.filename}：{e}")
        raise


def _run_ingest(kb_id: str, doc_ids: list[str], reset: bool, cb):
    db = SessionLocal()
    try:
        kb = db.get(KnowledgeBase, kb_id)
        if reset:
            # 清空集合内容而非删除集合：chroma 同进程 drop+recreate 有段落丢失的坑
            col = vectorstore.collection(kb_id)
            try:
                col.delete(where={"kb_id": kb_id})
            except Exception:
                vectorstore.drop_collection(kb_id)
            for doc in db.scalars(select(Document).where(Document.kb_id == kb_id)):
                doc.status, doc.chunks = "pending", 0
            db.commit()
        for doc_id in doc_ids:
            doc = db.get(Document, doc_id)
            if doc:
                _ingest_document(db, kb, doc, cb)
        _flush_search_cache()
    finally:
        db.close()


def _run_persona(kb_id: str, cb):
    db = SessionLocal()
    try:
        kb = db.get(KnowledgeBase, kb_id)
        col = vectorstore.collection(kb_id)
        try:
            col.delete(where={"kb_id": kb_id})
        except Exception:
            vectorstore.drop_collection(kb_id)
        db.query(Document).filter(Document.kb_id == kb_id).delete()
        docs = []
        for f in sorted(PERSONA_DIR.glob("*.md")):
            doc = Document(id=new_id(), kb_id=kb_id, filename=f.name, stored_path=str(f),
                           size=f.stat().st_size, status="pending", chunks=0, error="",
                           created_at=time(), updated_at=time())
            db.add(doc)
            docs.append(doc)
        db.commit()
        cb(0, f"同步 {len(docs)} 个档案文件")
        for doc in docs:
            _ingest_document(db, kb, doc, cb)
        _flush_search_cache()
    finally:
        db.close()


# ---------- 对外接口：仅提交任务，具体执行在任务线程里新开会话 ----------

def submit_ingest(kb_id: str, doc_ids: list[str]) -> str:
    db = SessionLocal()
    try:
        name = db.get(KnowledgeBase, kb_id).name
    finally:
        db.close()
    return tasks.submit(f"入库 {name}", len(doc_ids),
                        lambda cb: _run_ingest(kb_id, doc_ids, False, cb))


def submit_rebuild(kb_id: str) -> str:
    db = SessionLocal()
    try:
        name = db.get(KnowledgeBase, kb_id).name
        doc_ids = list(db.scalars(select(Document.id).where(Document.kb_id == kb_id)))
    finally:
        db.close()
    return tasks.submit(f"重建索引 {name}", len(doc_ids),
                        lambda cb: _run_ingest(kb_id, doc_ids, True, cb))


def submit_persona_sync(kb_id: str) -> str:
    db = SessionLocal()
    try:
        name = db.get(KnowledgeBase, kb_id).name
    finally:
        db.close()
    return tasks.submit(f"同步个人档案 {name}", 1, lambda cb: _run_persona(kb_id, cb))
