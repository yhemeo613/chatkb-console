# -*- coding: utf-8 -*-
"""全局路径、系统设置（settings.json）、安全配置

并发说明：设置文件在每个请求都会被读取（JWT 密钥校验），
必须保证 读写原子 + 进程内互斥，否则密钥会在并发瞬间漂移，导致 token 间歇性失效。
"""
import json
import os
import secrets
import tempfile
import threading
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent   # backend/
DATA_DIR = BACKEND_DIR / "data"                        # 运行时数据
UPLOAD_DIR = DATA_DIR / "uploads"                      # 上传的原始文档
CHROMA_DIR = Path(os.getenv("CHATKB_CHROMA_DIR") or (DATA_DIR / "chroma"))  # 向量库（测试可隔离）
PERSONA_DIR = DATA_DIR / "personal"                    # 个人档案（md 文件）
DB_PATH = DATA_DIR / "meta.db"                         # 元数据 SQLite
SETTINGS_PATH = DATA_DIR / "settings.json"             # 用户设置 + 密钥

PROJECT_ROOT = BACKEND_DIR.parent
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

OLLAMA_URL = "http://localhost:11434"
REDIS_URL = "redis://127.0.0.1:6379/0"                 # Windows 本机 Redis 服务

DEFAULT_SETTINGS = {
    "chat_model": "qwen3:4b",       # 生成回复用的大模型
    "embed_model": "bge-m3",        # 向量模型
    "chunk_size": 600,              # 分块目标长度（字符）
    "chunk_overlap": 100,           # 相邻块重叠
    "top_k": 6,                     # 检索条数
    "temperature": 0.8,             # 生成温度
    "rate_limit_per_min": 10,       # 每分钟回复生成次数上限（Redis 限流）
    "token_expire_hours": 72,       # JWT 有效期
    "jwt_secret": "",               # 首次启动自动生成并持久化
}

_settings_lock = threading.Lock()
_cache: dict | None = None   # 进程内缓存，读多写少

for d in (DATA_DIR, UPLOAD_DIR, CHROMA_DIR, PERSONA_DIR):
    d.mkdir(parents=True, exist_ok=True)


def _read_file() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}  # 读取失败按空处理（写侧用原子替换，正常不会发生）


def _write_file(settings: dict):
    """临时文件 + os.replace 原子替换，读者永远看不到半截 JSON"""
    fd, tmp = tempfile.mkstemp(dir=str(DATA_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_settings() -> dict:
    global _cache
    with _settings_lock:
        if _cache is not None:
            return dict(_cache)
        settings = {**DEFAULT_SETTINGS, **_read_file()}
        if not settings.get("jwt_secret"):
            settings["jwt_secret"] = secrets.token_hex(32)
            _write_file(settings)
        _cache = settings
        return dict(settings)


def save_settings(patch: dict) -> dict:
    global _cache
    with _settings_lock:
        settings = {**DEFAULT_SETTINGS, **_read_file()}
        for k in DEFAULT_SETTINGS:
            if k in patch and patch[k] is not None:
                settings[k] = patch[k]
        _write_file(settings)
        _cache = settings
        return dict(settings)
