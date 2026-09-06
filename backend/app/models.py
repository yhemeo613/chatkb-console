# -*- coding: utf-8 -*-
"""SQLAlchemy ORM 模型（表名/列名与旧 schema 兼容，新增表走 create_all）

RBAC：users -< user_roles >- roles -< role_menus >- menus（目录/菜单/按钮三级）
按钮节点携带 perm_code，作为 API 鉴权的最小权限单元。
"""
import time

from sqlalchemy import Column, Float, ForeignKey, Index, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase

from .config import DB_PATH


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id = Column(String(32), primary_key=True)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    nickname = Column(String(64), default="")
    is_superuser = Column(Integer, default=0)      # 超管绕过一切权限检查
    status = Column(String(16), default="active")  # active / disabled
    last_login_at = Column(Float)
    created_at = Column(Float, default=time.time)


class KnowledgeBase(Base):
    __tablename__ = "kbs"
    id = Column(String(32), primary_key=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    type = Column(String(16), nullable=False, default="docs")  # docs / persona
    embed_model = Column(String(64), nullable=False)
    chunk_size = Column(Integer, nullable=False)
    chunk_overlap = Column(Integer, nullable=False)
    created_at = Column(Float, nullable=False)


class Document(Base):
    __tablename__ = "documents"
    id = Column(String(32), primary_key=True)
    kb_id = Column(String(32), nullable=False, index=True)
    filename = Column(String(256), nullable=False)
    stored_path = Column(String(512), nullable=False)
    size = Column(Integer, default=0)
    status = Column(String(16), default="pending")  # pending/processing/done/failed
    chunks = Column(Integer, default=0)
    error = Column(Text, default="")
    created_at = Column(Float, nullable=False)
    updated_at = Column(Float, nullable=False)


class Role(Base):
    __tablename__ = "roles"
    id = Column(String(32), primary_key=True)
    name = Column(String(64), nullable=False)
    code = Column(String(64), unique=True, nullable=False)
    description = Column(Text, default="")
    is_builtin = Column(Integer, default=0)  # 内置角色不可删除
    created_at = Column(Float, default=time.time)


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id = Column(String(32), ForeignKey("users.id"), primary_key=True)
    role_id = Column(String(32), ForeignKey("roles.id"), primary_key=True)


class Menu(Base):
    __tablename__ = "menus"
    id = Column(String(32), primary_key=True)
    parent_id = Column(String(32), index=True)     # 顶级为 NULL
    name = Column(String(64), nullable=False)
    type = Column(String(8), nullable=False)       # dir / menu / button
    path = Column(String(128), default="")         # 前端路由，menu 类型必有
    icon = Column(String(32), default="")
    perm_code = Column(String(64), default="")     # 权限码：menu=页面权限, button=按钮权限
    sort = Column(Integer, default=0)
    visible = Column(Integer, default=1)
    created_at = Column(Float, default=time.time)


class RoleMenu(Base):
    __tablename__ = "role_menus"
    role_id = Column(String(32), ForeignKey("roles.id"), primary_key=True)
    menu_id = Column(String(32), ForeignKey("menus.id"), primary_key=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(32), default="")
    username = Column(String(64), default="")
    method = Column(String(8), default="")
    path = Column(String(256), default="")
    status_code = Column(Integer, default=0)
    ip = Column(String(64), default="")
    duration_ms = Column(Integer, default=0)
    created_at = Column(Float, default=time.time)


Index("ix_audit_created", AuditLog.created_at)


class LlmProvider(Base):
    """用户自配的大模型服务商（每用户隔离，API Key 加密存储）"""
    __tablename__ = "llm_providers"
    id = Column(String(32), primary_key=True)
    user_id = Column(String(32), nullable=False, index=True)
    name = Column(String(64), nullable=False)          # 展示名，如 "我的 DeepSeek"
    vendor = Column(String(32), nullable=False)        # 厂商编码，见 services/llm.py 预设
    base_url = Column(String(256), nullable=False)
    api_key_enc = Column(String(512), default="")      # Fernet 密文
    enabled = Column(Integer, default=1)
    extra_models = Column(Text, default="")            # 手动补充的模型名（换行分隔）
    created_at = Column(Float, default=time.time)


class LlmUsage(Base):
    """模型调用流水（本地/云端统一记录）"""
    __tablename__ = "llm_usage"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(32), nullable=False, index=True)
    username = Column(String(64), default="")
    vendor = Column(String(32), default="ollama")
    provider_id = Column(String(32), default="")
    model = Column(String(128), default="")
    kind = Column(String(16), default="chat")          # chat / embed
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    latency_ms = Column(Integer, default=0)
    ok = Column(Integer, default=1)
    error = Column(Text, default="")
    created_at = Column(Float, default=time.time)


Index("ix_usage_user_time", LlmUsage.user_id, LlmUsage.created_at)

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)

from sqlalchemy import event, text  # noqa: E402


@event.listens_for(engine, "connect")
def _set_wal(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


_LLM_USAGE_NEW_COLUMNS = {"username": "VARCHAR(64) DEFAULT ''"}

_USER_NEW_COLUMNS = {
    "nickname": "VARCHAR(64) DEFAULT ''",
    "is_superuser": "INTEGER DEFAULT 0",
    "status": "VARCHAR(16) DEFAULT 'active'",
    "last_login_at": "FLOAT",
}


def migrate():
    """轻量迁移：为旧 users 表补齐新增列（SQLite 只支持 ADD COLUMN）"""
    with engine.connect() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(users)"))}
        for col, ddl in _USER_NEW_COLUMNS.items():
            if col not in cols:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {ddl}"))
        if conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='llm_usage'")).scalar():
            ucols = {row[1] for row in conn.execute(text("PRAGMA table_info(llm_usage)"))}
            for col, ddl in _LLM_USAGE_NEW_COLUMNS.items():
                if col not in ucols:
                    conn.execute(text(f"ALTER TABLE llm_usage ADD COLUMN {col} {ddl}"))
        conn.commit()
