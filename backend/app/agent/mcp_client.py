# -*- coding: utf-8 -*-
"""
MCP（Model Context Protocol）客户端接入。

配置文件：backend/data/mcp_servers.json
{
  "servers": [
    {"name": "fs", "transport": "stdio",
     "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "D:/docs"]},
    {"name": "remote", "transport": "sse", "url": "http://127.0.0.1:9000/sse"}
  ]
}

设计：后台常驻 asyncio 事件循环线程；每个 server 一条会话；
MCP 工具桥接为 LangChain 工具（异步调用经 run_coroutine_threadsafe 投递）。
任一 server 连不上只记警告，不影响系统其它部分。
"""
import asyncio
import json
import threading
from pathlib import Path

from pydantic import Field

from ..config import DATA_DIR

MCP_CONFIG = DATA_DIR / "mcp_servers.json"

_loop: asyncio.AbstractEventLoop | None = None
_ready = threading.Event()
_sessions: dict[str, dict] = {}   # name -> {"tools": [...], "error": ""}
_lock = threading.Lock()


def _loop_runner(loop: asyncio.AbstractEventLoop):
    asyncio.set_event_loop(loop)
    loop.run_forever()


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        threading.Thread(target=_loop_runner, args=(_loop,), daemon=True).start()
        _ready.wait(timeout=2)
    return _loop


def load_config() -> dict:
    if not MCP_CONFIG.exists():
        return {"servers": []}
    try:
        return json.loads(MCP_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {"servers": []}


def save_config(cfg: dict):
    MCP_CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


async def _connect_server(spec: dict) -> dict:
    """连接单个 MCP server 并枚举工具（stdio / sse 两种传输）"""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.sse import sse_client

    transport = spec.get("transport", "stdio")
    if transport == "stdio":
        params = StdioServerParameters(command=spec["command"], args=spec.get("args", []))
        cm = stdio_client(params)
    else:
        cm = sse_client(spec["url"])

    async with cm as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_list = [{"name": t.name, "description": t.description or "",
                          "schema": (t.inputSchema or {})} for t in tools.tools]
            return {"tools": tool_list}


async def _call_tool(spec: dict, tool_name: str, arguments: dict) -> str:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.sse import sse_client

    transport = spec.get("transport", "stdio")
    if transport == "stdio":
        cm = stdio_client(StdioServerParameters(command=spec["command"], args=spec.get("args", [])))
    else:
        cm = sse_client(spec["url"])

    async with cm as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments or {})
            parts = []
            for item in result.content:
                if getattr(item, "text", None):
                    parts.append(item.text)
            return "\n".join(parts) or "（MCP 工具无文本输出）"


def refresh() -> list[dict]:
    """连接配置里的全部 server，返回每个的状态与工具清单"""
    _get_loop()
    cfg = load_config()
    status = []

    async def run_all():
        for spec in cfg.get("servers", []):
            name = spec.get("name", "unnamed")
            try:
                info = await asyncio.wait_for(_connect_server(spec), timeout=30)
                with _lock:
                    _sessions[name] = {**spec, **info}
                status.append({"name": name, "ok": True, "tools": info["tools"]})
            except Exception as e:
                with _lock:
                    _sessions.pop(name, None)
                status.append({"name": name, "ok": False, "error": str(e)[:200]})

    future = asyncio.run_coroutine_threadsafe(run_all(), _get_loop())
    return future.result(timeout=120)


def connected_tools() -> list[dict]:
    """全部已连接 server 的工具清单"""
    with _lock:
        return [{"server": name, **t} for name, s in _sessions.items() for t in s.get("tools", [])]


def get_server_spec(name: str) -> dict | None:
    with _lock:
        s = _sessions.get(name)
        return {k: v for k, v in s.items() if k != "tools"} if s else None


def build_mcp_tools() -> list:
    """把已连接的 MCP 工具桥接为 LangChain StructuredTool"""
    import json as _json

    tools = []
    for t in connected_tools():
        server, name = t["server"], t["name"]
        schema = t.get("schema") or {}
        fields = {}
        for pname, pspec in (schema.get("properties") or {}).items():
            fields[pname] = (str, Field(default="", description=str(pspec.get("description", ""))))

        Model = create_model(f"mcp_{server}_{name}_args", **fields) if fields else None

        def run(tool_server=server, tool_name=name, **kwargs) -> str:
            spec = get_server_spec(tool_server)
            if not spec:
                return f"MCP 服务 {tool_server} 未连接"
            fut = asyncio.run_coroutine_threadsafe(
                _call_tool(spec, tool_name, kwargs), _get_loop())
            try:
                return fut.result(timeout=60)
            except Exception as e:
                return f"MCP 调用失败：{e}"

        if Model is None:
            tools.append(StructuredTool.from_function(func=run, name=f"mcp_{name}",
                                                      description=f"[MCP:{server}] {t['description']}"))
        else:
            tools.append(StructuredTool.from_function(func=run, name=f"mcp_{name}",
                                                      description=f"[MCP:{server}] {t['description']}",
                                                      args_schema=Model))
    return tools


def create_model(*args, **kwargs):
    from pydantic import create_model as _cm
    return _cm(*args, **kwargs)  # 局部导入避免与 pydantic.Field 命名混淆
