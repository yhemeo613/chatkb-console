# -*- coding: utf-8 -*-
"""
HTTP 工具插件：backend/data/agent_plugins/*.json 即插件，热加载。

插件格式（OpenAI function 风格的极简版）：
{
  "name": "weather",
  "description": "查询城市天气",
  "method": "GET",
  "endpoint": "https://wttr.in/{city}?format=3",
  "params": {"city": "城市名，中文或拼音"},
  "headers": {}
}
endpoint 里的 {参数名} 会被替换；POST 时参数走 JSON body。
"""
import json
from pathlib import Path

import requests
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model

from ..config import DATA_DIR

PLUGINS_DIR = DATA_DIR / "agent_plugins"


def _load_plugin_files() -> list[dict]:
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for f in sorted(PLUGINS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("name") and data.get("endpoint"):
                out.append(data)
        except Exception:
            continue
    return out


def load_plugins() -> list[dict]:
    """插件清单（供前端展示）"""
    return [{k: v for k, v in p.items() if k != "headers"} for p in _load_plugin_files()]


def build_plugin_tools() -> list:
    """把插件 JSON 编译为 LangChain StructuredTool"""
    tools = []
    for spec in _load_plugin_files():
        tools.append(_compile(spec))
    return tools


def _compile(spec: dict):
    name = re_safe(spec["name"])
    desc = spec.get("description", name)
    params: dict = spec.get("params", {}) or {}
    method = (spec.get("method") or "GET").upper()
    endpoint = spec["endpoint"]
    headers = spec.get("headers", {}) or {}

    fields = {}
    for pname, pdesc in params.items():
        fields[pname] = (str, Field(default="", description=str(pdesc)))
    Model = create_model(f"{name}_args", **fields)

    def run(**kwargs) -> str:
        url = endpoint
        payload = {k: v for k, v in kwargs.items() if v}
        for k, v in payload.items():
            url = url.replace("{" + k + "}", str(v))
        try:
            if method == "GET":
                r = requests.get(url, headers=headers, params=payload, timeout=20)
            else:
                r = requests.request(method, url, headers=headers, json=payload, timeout=20)
            text = r.text
            return text[:2000] if r.status_code == 200 else f"HTTP {r.status_code}: {text[:300]}"
        except Exception as e:
            return f"插件调用失败：{e}"

    return StructuredTool.from_function(func=run, name=name, description=desc, args_schema=Model)


def re_safe(name: str) -> str:
    import re
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    return cleaned or "plugin_tool"
