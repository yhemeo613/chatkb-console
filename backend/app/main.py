# -*- coding: utf-8 -*-
"""FastAPI 入口：认证/RBAC/业务路由、审计日志中间件、APScheduler、SPA 托管"""
import logging
import time

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .config import FRONTEND_DIST
from .database import SessionLocal, bootstrap, get_db, init_db, new_id, now
from .models import AuditLog
from .routers import (agent, auth, chat, documents, ext, ext_db, ext_redis,
                      kbs, llm, ops, profiles, search, system, sys_menus, sys_roles,
                      sys_users, ws)
from .services.security import decode_token

logger = logging.getLogger("chatkb")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="聊天知识库系统", version="3.0.0")

app.include_router(auth.router)
app.include_router(system.router)
app.include_router(kbs.router)
app.include_router(documents.router)
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(profiles.router)
app.include_router(sys_users.router)
app.include_router(sys_roles.router)
app.include_router(sys_menus.router)
app.include_router(ops.router)
app.include_router(llm.router)
app.include_router(agent.router)
app.include_router(ext.router)
app.include_router(ext_db.router)
app.include_router(ext_redis.router)
app.include_router(ws.router)


class AuditMiddleware:
    """写操作审计（纯 ASGI 实现：不缓冲响应体，兼容 NDJSON 流式接口）"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] == "GET" or not scope["path"].startswith("/api"):
            await self.app(scope, receive, send)
            return
        start = time.time()
        status_holder = {"code": 0}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
            await send(message)

        await self.app(scope, receive, send_wrapper)

        # 响应结束后落审计（流式接口在流关闭后到达这里）
        try:
            user_id = username = ""
            headers = {k.decode(): v.decode() for k, v in scope.get("headers", [])}
            auth = headers.get("authorization", "")
            if auth.startswith("Bearer "):
                payload = decode_token(auth[7:])
                if payload:
                    user_id, username = payload["sub"], payload.get("username", "")
            if not username:
                username = "anonymous"
            client = scope.get("client")
            db = SessionLocal()
            try:
                db.add(AuditLog(
                    id=None, user_id=user_id, username=username,
                    method=scope["method"], path=scope["path"],
                    status_code=status_holder["code"],
                    ip=client[0] if client else "",
                    duration_ms=int((time.time() - start) * 1000),
                    created_at=now(),
                ))
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"审计日志写入失败（不影响请求）：{e}")


app.add_middleware(AuditMiddleware)


@app.on_event("startup")
def startup():
    # 先固定 JWT 密钥（settings.json 缺失时只生成一次），避免并发请求各自生成导致旧 token 失效
    from .config import load_settings
    load_settings()

    init_db()
    db = next(get_db())
    bootstrap(db)
    db.close()

    # 预热 Chroma，避免首个请求等待数秒
    from .models import KnowledgeBase
    from .services import vectorstore
    with SessionLocal() as s:
        for kb in s.query(KnowledgeBase):
            vectorstore.collection(kb.id).count()

    # APScheduler 定时任务：每小时清理过期任务历史
    from apscheduler.schedulers.background import BackgroundScheduler
    from .services import tasks
    sched = BackgroundScheduler(timezone="Asia/Shanghai")
    sched.add_job(tasks.cleanup_finished, "interval", hours=1, id="cleanup_tasks")
    sched.start()
    logger.info("后台调度器已启动（每小时清理过期任务）")


@app.exception_handler(404)
async def spa_fallback(request, exc):
    """非 /api 的未命中路径回退 index.html，支持前端 history 路由"""
    path = request.url.path
    if path.startswith("/api") or path.startswith("/ws"):
        return JSONResponse({"detail": getattr(exc, "detail", "Not Found")}, status_code=404)
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        # 入口文件禁缓存：构建更新后旧标签页刷新即可拿到新资源清单，避免白屏
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    return JSONResponse({"detail": "前端未构建：请先执行 cd frontend && npm run build"}, status_code=404)


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
