# -*- coding: utf-8 -*-
"""智能体 API：编排式回复（带执行轨迹）/ 工具清单 / 技能清单 / MCP 管理"""
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..agent import mcp_client, plugins, skills
from ..agent.flow import run_flow
from ..database import get_db
from ..services import llm
from ..services.security import get_current_user

router = APIRouter(prefix="/api/agent", tags=["智能体"],
                   dependencies=[Depends(get_current_user)])


class AgentReplyIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    person: str = ""
    history: str = ""
    model: str | None = None
    engine: str = "agent"       # agent / fast
    temperature: float | None = Field(default=None, ge=0, le=2)


def rate_limit(request: Request):
    from ..config import load_settings
    from ..services import cache
    ip = request.client.host if request.client else "unknown"
    limit = int(load_settings()["rate_limit_per_min"])
    if cache.incr_with_ttl(f"rl:agent:{ip}", 60) > limit:
        raise HTTPException(429, f"请求太频繁，每分钟最多 {limit} 次")


@router.post("/reply", dependencies=[Depends(rate_limit)])
def agent_reply(body: AgentReplyIn, user: dict = Depends(get_current_user),
                db: Session = Depends(get_db)):
    if body.engine not in ("agent", "fast"):
        raise HTTPException(400, "engine 必须是 agent 或 fast")
    from ..config import load_settings
    settings = load_settings()
    try:
        return run_flow(
            db, user_id=user["id"], username=user["username"],
            message=body.message, person=body.person, history=body.history,
            model_spec=body.model or settings["chat_model"],
            engine=body.engine,
            temperature=body.temperature if body.temperature is not None
                        else settings["temperature"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"智能体执行失败：{str(e)[:300]}")


@router.post("/reply/stream")
def agent_reply_stream(body: AgentReplyIn, user: dict = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """流式执行：每完成一个节点/工具即推送一行 NDJSON，前端实时渲染思维链路"""
    import queue
    import threading

    if body.engine not in ("agent", "fast"):
        raise HTTPException(400, "engine 必须是 agent 或 fast")
    from ..config import load_settings
    settings = load_settings()

    def gen():
        q: queue.Queue = queue.Queue()

        def emit(ev):
            q.put(ev)

        def worker():
            try:
                result = run_flow(
                    db, user_id=user["id"], username=user["username"],
                    message=body.message, person=body.person, history=body.history,
                    model_spec=body.model or settings["chat_model"],
                    engine=body.engine,
                    temperature=body.temperature if body.temperature is not None
                                else settings["temperature"],
                    emit=emit)
                q.put({"type": "done", "candidates": result["candidates"],
                       "sources": result["sources"], "skill": result["skill"],
                       "elapsed_ms": result["elapsed_ms"], "errors": result["errors"]})
            except Exception as e:
                q.put({"type": "error", "detail": str(e)[:300]})

        threading.Thread(target=worker, daemon=True).start()
        while True:
            try:
                ev = q.get(timeout=240)
            except queue.Empty:
                yield json.dumps({"type": "ping"}) + "\n"
                continue
            yield json.dumps(ev, ensure_ascii=False, default=str) + "\n"
            if ev.get("type") in ("done", "error"):
                break

    return StreamingResponse(gen(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@router.get("/tools")
def list_tools(user: dict = Depends(get_current_user)):
    """当前智能体可用的全部工具：内置 / HTTP 插件 / MCP"""
    from ..agent.tools.builtin import ToolContext, build_tools
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        ctx = ToolContext(db=db, user_id=user["id"])
        builtin = [{"name": t.name, "kind": "builtin", "description": t.description}
                   for t in build_tools(ctx)]
    finally:
        db.close()
    plugin = [{"name": f"plugin:{p['name']}", "kind": "plugin", "description": p.get("description", "")}
              for p in plugins.load_plugins()]
    mcp = [{"name": f"mcp:{t['server']}:{t['name']}", "kind": "mcp",
            "description": f"[{t['server']}] {t['description']}"} for t in mcp_client.connected_tools()]
    return {"builtin": builtin, "plugin": plugin, "mcp": mcp}


@router.get("/skills")
def list_skills(refresh: bool = False):
    return skills.load_skills(force=refresh)


@router.get("/mcp")
def mcp_status():
    cfg = mcp_client.load_config()
    connected = {t["server"] for t in mcp_client.connected_tools()}
    return {"config": cfg,
            "servers": [{"name": s.get("name"), "transport": s.get("transport", "stdio"),
                         "connected": s.get("name") in connected}
                        for s in cfg.get("servers", [])],
            "tools": mcp_client.connected_tools()}


@router.post("/mcp/refresh")
def mcp_refresh():
    try:
        return {"results": mcp_client.refresh()}
    except Exception as e:
        raise HTTPException(502, f"MCP 连接失败：{str(e)[:300]}")


@router.post("/mcp/servers")
def add_mcp_server(body: dict):
    cfg = mcp_client.load_config()
    if not body.get("name") or not body.get("command"):
        raise HTTPException(400, "需要 name 与 command（stdio 模式）")
    cfg.setdefault("servers", []).append({
        "name": body["name"], "transport": "stdio",
        "command": body["command"], "args": body.get("args", []),
    })
    mcp_client.save_config(cfg)
    return {"ok": True, "config": cfg}
