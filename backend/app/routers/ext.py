# -*- coding: utf-8 -*-
"""技能 / 插件 / 画布配置 / MCP 扩展管理（文件级 CRUD，即改即生效）"""
import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..agent import mcp_client, skills
from ..agent.canvas import load_canvas as _load_canvas, save_canvas as _save_canvas
from ..agent.flow import run_flow
from ..agent.plugins import PLUGINS_DIR, load_plugins
from ..config import DATA_DIR
from ..services.security import get_current_user, require_perm

router = APIRouter(prefix="/api/ext", tags=["扩展管理"])


SAFE_NAME = re.compile(r"^[\w\u4e00-\u9fff\-]{1,48}$")


def _safe_stem(name: str) -> str:
    if not SAFE_NAME.match(name or ""):
        raise HTTPException(400, "名称只能包含中文、字母、数字、下划线、连字符")
    return name


# ================= 技能管理 =================

@router.get("/skills", dependencies=[Depends(require_perm("ext:skills"))])
def list_skill_files():
    """内置技能（只读）+ 自定义技能文件，一起返回"""
    out = [{"file": "", "builtin": True, **{k: v for k, v in s.items()}}
           for s in skills.load_skills() if s.get("source") == "builtin"]
    skills_dir = Path(skills.SKILLS_DIR)
    skills_dir.mkdir(parents=True, exist_ok=True)
    for f in sorted(skills_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            out.append({"file": f.name, "builtin": False, **data})
        except Exception:
            out.append({"file": f.name, "name": f.stem, "builtin": False, "error": "文件损坏"})
    return out


class SkillIn(BaseModel):
    name: str = Field(min_length=1, max_length=48)
    match: list[str] = []
    prompt: str = ""
    example: str = ""


@router.post("/skills/{stem}", dependencies=[Depends(require_perm("ext:skills"))])
def save_skill(stem: str, body: SkillIn):
    stem = _safe_stem(stem)
    path = Path(skills.SKILLS_DIR) / f"{stem}.json"
    path.write_text(json.dumps({
        "name": body.name, "match": body.match,
        "prompt": body.prompt, "example": body.example,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    skills.load_skills(force=True)
    return {"file": path.name}


@router.delete("/skills/{stem}", dependencies=[Depends(require_perm("ext:skills"))])
def delete_skill(stem: str):
    stem = _safe_stem(stem)
    path = Path(skills.SKILLS_DIR) / f"{stem}.json"
    if not path.exists():
        raise HTTPException(404, "技能文件不存在")
    path.unlink()
    skills.load_skills(force=True)
    return {"ok": True}


# ================= 插件管理 =================

def _plugin_path(stem: str) -> Path:
    stem = _safe_stem(stem)
    return PLUGINS_DIR / f"{stem}.json"


@router.get("/plugins", dependencies=[Depends(require_perm("ext:plugins"))])
def list_plugin_files():
    return load_plugins()


class PluginIn(BaseModel):
    name: str = Field(min_length=1, max_length=48)
    description: str = ""
    method: str = "GET"
    endpoint: str = Field(min_length=1)
    params: dict = {}
    headers: dict = {}


@router.post("/plugins/{stem}", dependencies=[Depends(require_perm("ext:plugins"))])
def save_plugin(stem: str, body: PluginIn):
    path = _plugin_path(stem)
    if body.method.upper() not in ("GET", "POST", "PUT", "DELETE"):
        raise HTTPException(400, "method 不支持")
    path.write_text(json.dumps({
        "name": body.name, "description": body.description,
        "method": body.method.upper(), "endpoint": body.endpoint,
        "params": body.params, "headers": body.headers,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"file": path.name}


@router.delete("/plugins/{stem}", dependencies=[Depends(require_perm("ext:plugins"))])
def delete_plugin(stem: str):
    path = _plugin_path(stem)
    if not path.exists():
        raise HTTPException(404, "插件不存在")
    path.unlink()
    return {"ok": True}


# ================= 编排画布 =================

@router.get("/canvas", dependencies=[Depends(get_current_user)])
def get_canvas():
    return _load_canvas()


@router.put("/canvas", dependencies=[Depends(require_perm("ext:canvas"))])
def save_canvas(body: dict):
    nodes = body.get("nodes") or []
    if not any(n.get("type") == "start" for n in nodes):
        raise HTTPException(400, "画布必须包含「开始」节点")
    if not any(n.get("type") == "answer" for n in nodes):
        raise HTTPException(400, "画布必须包含「输出」节点")
    _save_canvas({"version": 2, "nodes": nodes,
                  "edges": body.get("edges") or []})
    return _load_canvas()


@router.post("/canvas/test", dependencies=[Depends(require_perm("ext:canvas"))])
def test_canvas(body: dict, user: dict = Depends(get_current_user)):
    db = __import__("app.database", fromlist=["SessionLocal"]).SessionLocal()
    try:
        return run_flow(db, user_id=user["id"], username=user["username"],
                        message=body.get("message") or "在吗？周末有空吗",
                        person=body.get("person", ""), history="",
                        model_spec=body.get("model") or "", engine="agent")
    finally:
        db.close()


# ================= MCP 管理（补删除/更新） =================

@router.put("/mcp/servers/{name}", dependencies=[Depends(require_perm("ext:mcp"))])
def update_mcp_server(name: str, body: dict):
    cfg = mcp_client.load_config()
    for s in cfg.get("servers", []):
        if s.get("name") == name:
            s["command"] = body.get("command") or s.get("command")
            s["args"] = body.get("args", s.get("args", []))
            mcp_client.save_config(cfg)
            return {"ok": True}
    raise HTTPException(404, "server 不存在")


@router.delete("/mcp/servers/{name}", dependencies=[Depends(require_perm("ext:mcp"))])
def delete_mcp_server(name: str):
    cfg = mcp_client.load_config()
    before = len(cfg.get("servers", []))
    cfg["servers"] = [s for s in cfg.get("servers", []) if s.get("name") != name]
    if len(cfg["servers"]) == before:
        raise HTTPException(404, "server 不存在")
    mcp_client.save_config(cfg)
    return {"ok": True}
