# -*- coding: utf-8 -*-
"""数据库初始化、种子数据（三级菜单树 + 默认角色 + 管理员）"""
import time
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .config import PERSONA_DIR, PROJECT_ROOT, UPLOAD_DIR
from .models import (Base, Document, KnowledgeBase, LlmProvider, Menu, Role,
                     RoleMenu, User, UserRole, engine, migrate)
from .services.security import hash_password

# 平台内置模型 Key 从环境变量读取（CHATKB_MINIMAX_KEY），未配置则不创建内置服务商。
# 本地部署可将密钥写入 backend/data/minimax_key.txt（该目录不入库）。
def _builtin_minimax_key() -> str:
    import os
    key = os.getenv("CHATKB_MINIMAX_KEY", "").strip()
    if key:
        return key
    f = Path(__file__).resolve().parent.parent / "data" / "minimax_key.txt"
    if f.exists():
        return f.read_text(encoding="utf-8").strip()
    return ""

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def now() -> float:
    return time.time()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def init_db():
    migrate()
    Base.metadata.create_all(engine)


# ---------- 三级菜单种子 ----------
# (key, parent_key, name, type, path, icon, perm_code, sort)
MENU_SEED = [
    ("dashboard", None, "工作台", "menu", "/dashboard", "dashboard", "", 1),
    ("llm", None, "模型中心", "menu", "/llm", "api", "", 50),
    ("ext_center", None, "扩展中心", "dir", "", "appstore", "", 80),
    ("ext_db", "ext_center", "数据库管理", "menu", "/ext/db", "database", "ext:db", 1),
    ("ext_redis", "ext_center", "Redis管理", "menu", "/ext/redis", "task", "ext:redis", 2),
    ("ext_skills", "ext_center", "技能管理", "menu", "/ext/skills", "safety", "ext:skills", 3),
    ("ext_plugins", "ext_center", "插件管理", "menu", "/ext/plugins", "appstore", "ext:plugins", 4),
    ("ext_mcp", "ext_center", "MCP接入", "menu", "/ext/mcp", "api", "ext:mcp", 5),
    ("ext_canvas", "ext_center", "编排画布", "menu", "/ext/canvas", "monitor", "ext:canvas", 6),
    ("kb_center", None, "知识库中心", "dir", "", "database", "", 10),
    ("kb", "kb_center", "知识库管理", "menu", "/kbs", "database", "kb", 1),
    ("kb_create", "kb", "新建知识库", "button", "", "", "kb:create", 1),
    ("kb_upload", "kb", "上传文档", "button", "", "", "kb:upload", 2),
    ("kb_rebuild", "kb", "重建索引", "button", "", "", "kb:rebuild", 3),
    ("kb_delete", "kb", "删除知识库", "button", "", "", "kb:delete", 4),
    ("search", "kb_center", "语义搜索", "menu", "/search", "search", "", 2),
    ("reply", "kb_center", "对话回复", "menu", "/reply", "message", "", 3),
    ("profiles", "kb_center", "个人档案", "menu", "/profiles", "profile", "profile", 4),
    ("profile_edit", "profiles", "档案编辑", "button", "", "", "profile:manage", 1),
    ("sys_center", None, "系统管理", "dir", "", "setting", "", 90),
    ("sys_user", "sys_center", "账号管理", "menu", "/system/users", "user", "sys:user", 1),
    ("sys_user_create", "sys_user", "新增账号", "button", "", "", "sys:user:create", 1),
    ("sys_user_update", "sys_user", "编辑账号", "button", "", "", "sys:user:update", 2),
    ("sys_user_delete", "sys_user", "删除账号", "button", "", "", "sys:user:delete", 3),
    ("sys_user_reset", "sys_user", "重置密码", "button", "", "", "sys:user:reset_pwd", 4),
    ("sys_role", "sys_center", "角色管理", "menu", "/system/roles", "team", "sys:role", 2),
    ("sys_role_create", "sys_role", "新增角色", "button", "", "", "sys:role:create", 1),
    ("sys_role_update", "sys_role", "编辑角色", "button", "", "", "sys:role:update", 2),
    ("sys_role_delete", "sys_role", "删除角色", "button", "", "", "sys:role:delete", 3),
    ("sys_menu", "sys_center", "菜单管理", "menu", "/system/menus", "appstore", "sys:menu", 3),
    ("sys_menu_create", "sys_menu", "新增菜单", "button", "", "", "sys:menu:create", 1),
    ("sys_menu_update", "sys_menu", "编辑菜单", "button", "", "", "sys:menu:update", 2),
    ("sys_menu_delete", "sys_menu", "删除菜单", "button", "", "", "sys:menu:delete", 3),
    ("ops_center", None, "运维监控", "dir", "", "monitor", "", 95),
    ("ops_status", "ops_center", "服务状态", "menu", "/ops/status", "monitor", "ops:status", 1),
    ("ops_tasks", "ops_center", "任务中心", "menu", "/ops/tasks", "task", "ops:tasks", 2),
    ("ops_logs", "ops_center", "操作日志", "menu", "/ops/logs", "log", "ops:logs", 3),
]

# 默认角色：(code, name, description, is_builtin, 授权的菜单 key 列表)
ROLE_SEED = [
    ("super_admin", "超级管理员", "拥有全部权限（超管账号直接绕过检查）", 1,
     [m[0] for m in MENU_SEED]),
    ("kb_admin", "知识管理员", "管理知识库、文档与个人档案", 1,
     ["dashboard", "kb_center", "kb", "kb_create", "kb_upload", "kb_rebuild", "kb_delete",
      "search", "reply", "profiles", "profile_edit"]),
    ("user", "普通用户", "使用语义搜索与对话回复", 1,
     ["dashboard", "kb_center", "search", "reply"]),
    ("ops", "运维员", "监控服务状态、任务与操作日志，管理数据库/Redis/扩展", 1,
     ["dashboard", "ops_center", "ops_status", "ops_tasks", "ops_logs",
      "ext_center", "ext_db", "ext_redis", "ext_skills", "ext_plugins", "ext_mcp", "ext_canvas"]),
]

DEFAULT_ROLE_CODE = "user"  # 自主注册的默认角色


def bootstrap(db: Session):
    """首次初始化：管理员、默认知识库、菜单树、角色授权、平台内置模型服务商"""
    # 平台内置 MiniMax 服务商（user_id='' 表示系统级，全员可用、仅超管可看 Key）
    from .services.llm import VENDOR_PRESETS, encrypt_key
    if _builtin_minimax_key() and not db.scalar(
            select(LlmProvider.id).where(LlmProvider.user_id == "",
                                         LlmProvider.vendor == "minimax")):
        db.add(LlmProvider(
            id=new_id(), user_id="", name="平台内置 · MiniMax", vendor="minimax",
            base_url=VENDOR_PRESETS["minimax"]["base_url"],
            api_key_enc=encrypt_key(_builtin_minimax_key()),
            enabled=1, extra_models="MiniMax-Text-01\nabab6.5s-chat", created_at=now(),
        ))

    if db.scalar(select(Menu.id).limit(1)) is None:
        ids = {}
        for key, parent, name, mtype, path, icon, perm, sort in MENU_SEED:
            m = Menu(id=new_id(), parent_id=ids.get(parent), name=name, type=mtype,
                     path=path, icon=icon, perm_code=perm, sort=sort,
                     visible=1, created_at=now())
            db.add(m)
            ids[key] = m.id
        db.flush()

        key_by_id = {v: k for k, v in ids.items()}
        menu_key_by_menu_id = {m.id: key_by_id.get(m.id, "") for m in db.scalars(select(Menu))}
        for code, name, desc, builtin, keys in ROLE_SEED:
            role = Role(id=new_id(), name=name, code=code, description=desc,
                        is_builtin=builtin, created_at=now())
            db.add(role)
            db.flush()
            if code == "super_admin":
                # 超管角色关联全部菜单（超管用户本身也直接绕过检查）
                db.add_all([RoleMenu(role_id=role.id, menu_id=mid) for mid in menu_key_by_menu_id])
            else:
                wanted = {ids[k] for k in keys if k in ids}
                db.add_all([RoleMenu(role_id=role.id, menu_id=mid)
                            for mid in wanted])

    if db.scalar(select(User.id).limit(1)) is None:
        admin = User(id=new_id(), username="admin", nickname="管理员",
                     password_hash=hash_password("admin123"), is_superuser=1,
                     status="active", created_at=now())
        db.add(admin)
        role = db.scalar(select(Role).where(Role.code == "super_admin"))
        if role:
            db.add(UserRole(user_id=admin.id, role_id=role.id))

    # 旧库升级：确保 admin 是超管且挂着超管角色
    admin = db.scalar(select(User).where(User.username == "admin"))
    if admin and not admin.is_superuser:
        admin.is_superuser = 1
        role = db.scalar(select(Role).where(Role.code == "super_admin"))
        if role and not db.scalar(select(UserRole).where(
                UserRole.user_id == admin.id, UserRole.role_id == role.id)):
            db.add(UserRole(user_id=admin.id, role_id=role.id))

    # ---- 存量库迁移：补插「扩展中心」菜单并授权（幂等） ----
    if not db.scalar(select(Menu.id).where(Menu.name == "扩展中心")):
        ext_ids = {}
        for key, parent, name, mtype, path, icon, perm, sort in MENU_SEED:
            if key == "ext_center" or key.startswith("ext_"):
                m = Menu(id=new_id(),
                         parent_id=(ext_ids.get(parent) if key != "ext_center" else None),
                         name=name, type=mtype, path=path, icon=icon, perm_code=perm,
                         sort=sort, visible=1, created_at=now())
                db.add(m)
                db.flush()
                ext_ids[key] = m.id
        db.flush()
        for role in db.query(Role):
            if role.code in ("super_admin", "ops"):
                db.add_all([RoleMenu(role_id=role.id, menu_id=mid) for mid in ext_ids.values()])
        db.flush()

    # ---- 旧版文件迁移（首次） ----
    if db.scalar(select(KnowledgeBase.id).limit(1)) is None:
        docs_kb, persona_kb = new_id(), new_id()
        db.add_all([
            KnowledgeBase(id=docs_kb, name="沟通书籍", description="说话、沟通、情商类书籍文档",
                          type="docs", embed_model="bge-m3", chunk_size=600, chunk_overlap=100, created_at=now()),
            KnowledgeBase(id=persona_kb, name="个人档案", description="人设、说话风格、关系档案、雷区（回复时必带）",
                          type="persona", embed_model="bge-m3", chunk_size=800, chunk_overlap=120, created_at=now()),
        ])
        legacy_personal = PROJECT_ROOT / "personal"
        if legacy_personal.exists():
            for f in legacy_personal.glob("*.md"):
                shutil.copy(f, PERSONA_DIR / f.name)
        legacy_kb = PROJECT_ROOT / "knowledge"
        if legacy_kb.exists():
            for f in legacy_kb.iterdir():
                if f.is_file() and f.suffix.lower() in {".pdf", ".epub", ".docx", ".txt", ".md", ".html", ".htm"}:
                    dest_dir = Path(UPLOAD_DIR) / docs_kb
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy(f, dest_dir / f.name)
                    db.add(Document(id=new_id(), kb_id=docs_kb, filename=f.name,
                                    stored_path=str(dest_dir / f.name), size=f.stat().st_size,
                                    status="pending", chunks=0, error="",
                                    created_at=now(), updated_at=now()))
    db.commit()


import shutil  # noqa: E402
