# -*- coding: utf-8 -*-
"""数据库可视化：表结构 / 行数据浏览 / 只读 SQL 控制台（禁止任何写操作）"""
import re
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..config import DB_PATH
from ..services.security import require_perm

router = APIRouter(prefix="/api/ext/db", tags=["数据库管理"],
                   dependencies=[Depends(require_perm("ext:db"))])

conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10)
conn.row_factory = sqlite3.Row


def _q(sql: str, params=()):
    return conn.execute(sql, params).fetchall()


@router.get("/tables")
def list_tables():
    tables = [r[0] for r in _q(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    out = []
    for t in tables:
        count = _q(f'SELECT COUNT(*) c FROM "{t}"')[0]["c"]
        cols = [{"name": c[1], "type": c[2]} for c in _q(f'PRAGMA table_info("{t}")')]
        out.append({"name": t, "rows": count, "columns": cols})
    return out


@router.get("/rows")
def list_rows(table: str, page: int = 1, size: int = 20):
    if not re.fullmatch(r"[\w]+", table or ""):
        raise HTTPException(400, "非法表名")
    exists = _q("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    if not exists:
        raise HTTPException(404, "表不存在")
    total = _q(f'SELECT COUNT(*) c FROM "{table}"')[0]["c"]
    rows = _q(f'SELECT * FROM "{table}" LIMIT ? OFFSET ?', (size, (page - 1) * size))
    cols = rows[0].keys() if rows else [c["name"] for c in _q(f'PRAGMA table_info("{table}")')]
    return {"columns": list(cols),
            "items": [[r[c] for c in cols] for r in rows],
            "total": total, "page": page, "size": size}


class QueryIn(BaseModel):
    sql: str


@router.post("/query")
def run_query(body: QueryIn):
    """只读 SQL 控制台：仅允许 SELECT / PRAGMA / EXPLAIN，禁止分号多语句"""
    sql = (body.sql or "").strip().rstrip(";").strip()
    if not sql:
        raise HTTPException(400, "SQL 不能为空")
    if ";" in sql:
        raise HTTPException(400, "一次只允许执行一条语句")
    head = sql.split(None, 1)[0].lower()
    if head not in ("select", "pragma", "explain"):
        raise HTTPException(400, "控制台仅允许只读查询（SELECT / PRAGMA / EXPLAIN）")
    t0 = time.time()
    cur = conn.execute(sql)
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = cur.fetchmany(200)
    return {"columns": cols, "items": [list(r) for r in rows],
            "row_count": len(rows), "ms": int((time.time() - t0) * 1000)}


import time  # noqa: E402
