# -*- coding: utf-8 -*-
"""智能体内置工具：供 LangGraph ReAct 节点绑定的 LangChain 工具

工具签名刻意做成「上下文注入 + 显式参数」：检索类工具需要访问数据库与用户身份，
通过 ToolContext 闭包注入，而不是让模型自己猜。
"""
import time
from dataclasses import dataclass
from typing import Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...config import PERSONA_DIR
from ...services import embeddings, vectorstore


@dataclass
class ToolContext:
    """一次智能体请求的运行时上下文"""
    db: Session
    user_id: str
    person: str = ""
    history: str = ""
    trace: list | None = None

    def log(self, tool: str, detail: str):
        if self.trace is not None:
            self.trace.append({"node": "tool", "tool": tool, "detail": detail[:400],
                               "ms": int(time.time() * 1000) % 100000})


def _search_kb(ctx: ToolContext, kb_type: str, query: str, top_k: int = 4) -> str:
    out = []
    from ...models import KnowledgeBase
    for kb in ctx.db.query(KnowledgeBase).filter(KnowledgeBase.type == kb_type):
        emb = embeddings.embed_one(query, kb.embed_model)
        for h in vectorstore.query(kb.id, emb, top_k):
            src = h["metadata"].get("source", "")
            out.append(f"[{src}]\n{h['text']}")
    return "\n\n---\n\n".join(out[:top_k]) or "（没有检索到相关内容）"


# ---------- 工具 1：知识库检索 ----------

class KbSearchInput(BaseModel):
    query: str = Field(description="要检索的话题关键词，例：如何婉拒邀约、领导表扬回应")
    scope: str = Field(default="book", description="检索范围：book=沟通书籍知识, persona=用户个人档案")


def make_kb_search_tool(ctx: ToolContext) -> StructuredTool:
    def run(query: str, scope: str = "book") -> str:
        kb_type = "persona" if scope == "persona" else "docs"
        result = _search_kb(ctx, kb_type, query)
        ctx.log("kb_search", f"scope={scope} query={query} -> {len(result)} 字")
        return result
    return StructuredTool.from_function(
        func=run, name="kb_search",
        description="检索沟通知识库（书籍话术）或用户个人档案（人设/关系/雷区）。回答前建议先查一遍。",
        args_schema=KbSearchInput,
    )


# ---------- 工具 2：关系档案查询 ----------

class ProfileInput(BaseModel):
    person: str = Field(description="对方称呼，例：老妈、同事小王")


def make_profile_tool(ctx: ToolContext) -> StructuredTool:
    def run(person: str = "") -> str:
        name = (person or ctx.person or "").strip()
        if not name:
            return "（未提供对方称呼）"
        hits = []
        for f in sorted(PERSONA_DIR.glob("*.md")):
            raw = f.read_text(encoding="utf-8", errors="ignore")
            if name in raw[:200] or f"name: {name}" in raw:
                hits.append(raw)
        result = "\n\n---\n\n".join(hits[:2]) or f"（没有找到「{name}」的关系档案）"
        ctx.log("profile_lookup", f"person={name} -> {len(hits)} 份档案")
        return result
    return StructuredTool.from_function(
        func=run, name="relationship_profile",
        description="查询与某人的关系档案（性格、沟通策略、雷区、大事记）。涉及具体的人时先调用。",
        args_schema=ProfileInput,
    )


# ---------- 工具 3：历史对话上下文 ----------

class HistoryInput(BaseModel):
    keyword: str = Field(description="要回忆的话题关键词")


def make_history_tool(ctx: ToolContext) -> StructuredTool:
    def run(keyword: str = "") -> str:
        if not ctx.history:
            return "（本次没有历史对话）"
        rel = [line for line in ctx.history.splitlines() if keyword in line] if keyword \
            else ctx.history.splitlines()
        result = "\n".join(rel[-10:]) or "（历史对话中没有相关内容）"
        ctx.log("history_recall", f"keyword={keyword} -> {len(rel)} 行")
        return result
    return StructuredTool.from_function(
        func=run, name="history_recall",
        description="回顾与对方之前的聊天记录，保持回复连贯。",
        args_schema=HistoryInput,
    )


# ---------- 工具 4：当前时间 ----------

def make_now_tool(ctx: ToolContext) -> StructuredTool:
    def run() -> str:
        now = time.strftime("%Y-%m-%d %H:%M %A")
        ctx.log("now", now)
        return f"当前时间：{now}"
    return StructuredTool.from_function(
        func=run, name="current_time",
        description="获取当前日期时间（节日祝福、约定时间时有用）。",
    )


def build_tools(ctx: ToolContext, extra_tools: Optional[list] = None) -> list:
    tools = [
        make_kb_search_tool(ctx),
        make_profile_tool(ctx),
        make_history_tool(ctx),
        make_now_tool(ctx),
    ]
    if extra_tools:
        tools += extra_tools
    return tools
