# -*- coding: utf-8 -*-
"""
智能体编排（LangGraph StateGraph）

图结构：
    retrieve ─▶ research(可选 ReAct 工具循环) ─▶ draft ─▶ bump ─▶ review ─▶ finalize
                                                              │ 不通过且未重写 ▲
                                                              ▼              │
                                                           redraft ──────────┘

- retrieve：确定性检索（个人档案 + 书籍知识）+ 技能匹配
- research：ReAct 循环，模型自主调用工具（内置 / HTTP 插件 / MCP），最多 3 轮
- draft / redraft：按技能纪律起草候选；被质检否决时带原因重写一次
- review：雷区 / 金钱承诺 / 说教门控
- 全部 LLM 调用统一落 LlmUsage 用量流水，执行轨迹随响应返回

模型寻址："provider_id|model"（云端）/ "ollama|model" / 裸模型名（本地）
"""
import json
import re
import time
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from ..config import OLLAMA_URL, load_settings
from ..models import LlmProvider
from ..services import embeddings, llm, vectorstore
from . import mcp_client, skills
from .canvas import load_canvas
from .plugins import build_plugin_tools
from .tools.builtin import ToolContext, build_tools

DRAFT_RULES = """你是用户的微信高情商回复助手。根据提供的资料和对话上下文，用用户的口吻生成 3 个候选回复：
1. 稳妥得体版  2. 幽默拉近距离版  3. 简短直接版

要求：
- 每条只输出回复本身，以"1.""2.""3."开头，不要解释、不要客套前言
- 资料中的【雷区/禁忌】绝对不能碰
- 涉及具体的人和事时优先参考【个人档案】
- 沟通技巧参考【沟通知识】，但不要生搬硬套
- 像正常人发微信：口语化、短句，长度一般不超过两三句
"""


class AgentState(TypedDict):
    message: str
    person: str
    history: str
    user_id: str
    username: str
    model_spec: str
    temperature: float
    engine: str                       # fast / agent
    skill_names: list
    skill_prompt: str
    persona_ctx: str
    kb_ctx: str
    tool_research: str
    candidates: list
    review: dict
    redraft_count: int
    candidates_final: list
    trace: Annotated[list, lambda a, b: (a or []) + (b or [])]
    errors: Annotated[list, lambda a, b: (a or []) + (b or [])]


# ---------- 模型解析（多厂商统一） ----------

def resolve_model(db, user_id: str, model_spec: str, temperature: float):
    settings = load_settings()
    if "|" in model_spec:
        provider_id, model = model_spec.split("|", 1)
    else:
        provider_id, model = "ollama", model_spec or settings["chat_model"]

    if provider_id == "ollama":
        return (ChatOpenAI(model=model, base_url=f"{OLLAMA_URL}/v1", api_key="ollama",
                           temperature=temperature, timeout=600),
                "ollama", "")
    p = db.get(LlmProvider, provider_id)
    if not p or p.user_id not in (user_id, ""):
        raise ValueError(f"模型服务商 {provider_id} 不存在")
    if not p.enabled:
        raise ValueError(f"服务商「{p.name}」已停用")
    return (ChatOpenAI(model=model, base_url=p.base_url,
                       api_key=llm.decrypt_key(p.api_key_enc) or "none",
                       temperature=temperature, timeout=600),
            p.vendor, p.id)


def _invoke(db, user_id, username, model_pack, messages, node, trace):
    model, vendor, provider_id = model_pack
    t0 = time.time()
    resp = model.invoke(messages)
    meta = getattr(resp, "usage_metadata", None) or {}
    usage = {"prompt_tokens": meta.get("input_tokens", 0),
             "completion_tokens": meta.get("output_tokens", 0),
             "total_tokens": meta.get("total_tokens", 0),
             "latency_ms": int((time.time() - t0) * 1000)}
    llm.record_usage(db, user_id, vendor, provider_id,
                     getattr(model, 'model_name', None) or 'fake', "chat",
                     usage, username=username)
    trace.append({"node": node, "detail": f"LLM {usage['total_tokens']} tokens / {usage['latency_ms']}ms",
                  "ms": usage["latency_ms"]})
    return resp


# ---------- 节点 ----------

def node_retrieve(ctx: ToolContext, model_pack):
    def run(state: AgentState) -> dict:
        t0 = time.time()
        trace = []
        from ..models import KnowledgeBase
        persona_ctx, kb_ctx = [], []
        for kb in ctx.db.query(KnowledgeBase):
            emb = embeddings.embed_one(state["message"], kb.embed_model)
            for h in vectorstore.query(kb.id, emb, 4):
                line = f"[{h['metadata'].get('source', '')}]\n{h['text']}"
                (persona_ctx if kb.type == "persona" else kb_ctx).append(line)

        hits = skills.match_skills(state["message"])
        trace.append({"node": "retrieve",
                      "detail": f"个人档案 {len(persona_ctx)} 段 / 书籍知识 {len(kb_ctx)} 段 / "
                                f"技能：{'、'.join(h['name'] for h in hits) or '通用高情商'}",
                      "ms": int((time.time() - t0) * 1000)})
        return {"persona_ctx": "\n\n---\n\n".join(persona_ctx[:4]),
                "kb_ctx": "\n\n---\n\n".join(kb_ctx[:6]),
                "skill_names": [h["name"] for h in hits] or ["通用高情商"],
                "skill_prompt": skills.skill_prompt(state["message"]),
                "trace": trace}
    return run


def node_research(ctx: ToolContext, model_pack, max_steps: int = 3):
    """ReAct 工具循环（engine=agent 且画布启用该节点才执行）"""
    def run(state: AgentState) -> dict:
        if state.get("engine") != "agent":
            return {"tool_research": "", "trace": []}
        t0 = time.time()
        trace, errors = [], []
        tools = build_tools(ctx, extra_tools=build_plugin_tools() + mcp_client.build_mcp_tools())
        tool_map = {t.name: t for t in tools}
        try:
            researcher = model_pack[0].bind_tools(tools)
        except Exception:
            # 模型不支持 function calling 时退化为直接生成（跳过工具轮）
            researcher = model_pack[0]
        messages = [
            SystemMessage(content="你是回复研究员，为起草高情商微信回复收集情报。"
                                  "可用工具：kb_search 查话术、relationship_profile 查对方档案、"
                                  "history_recall 回忆上下文、current_time 看时间。"
                                  "最多 3 轮，之后输出要点清单。"),
            HumanMessage(content=f"对方是「{state['person'] or '未知'}」，发来：{state['message']}"),
        ]
        collected = []
        for step in range(1, max_steps + 1):
            try:
                resp = researcher.invoke(messages)
            except Exception as e:
                errors.append(f"research: {str(e)[:200]}")
                break
            calls = getattr(resp, "tool_calls", None) or []
            if not calls:
                collected.append(str(resp.content)[:800])
                trace.append({"node": "research", "step": step, "detail": "研究完成",
                              "ms": int((time.time() - t0) * 1000)})
                break
            messages.append(resp)
            for call in calls:
                tool = tool_map.get(call["name"])
                try:
                    result = tool.invoke(call.get("args") or {}) if tool else f"未知工具 {call['name']}"
                except Exception as e:
                    result = f"工具执行失败：{e}"
                trace.append({"node": "research", "step": step, "tool": call["name"],
                              "detail": json.dumps(call.get("args", {}), ensure_ascii=False)[:300]
                                        + " → " + str(result)[:180],
                              "ms": int((time.time() - t0) * 1000)})
                messages.append(ToolMessage(content=str(result)[:2000],
                                            tool_call_id=call.get("id") or call["name"]))
                collected.append(f"[{call['name']}] {str(result)[:500]}")
        return {"tool_research": "\n".join(collected)[:3000], "trace": trace, "errors": errors}
    return run


def _context_block(state: AgentState) -> str:
    parts = [f"【对方消息】\n{state['message']}"]
    if state.get("person"):
        parts.append(f"【对方是谁】{state['person']}")
    if state.get("history"):
        parts.append(f"【之前的聊天】\n{state['history']}")
    if state.get("persona_ctx"):
        parts.append("【个人档案】\n" + state["persona_ctx"])
    if state.get("kb_ctx"):
        parts.append("【沟通知识】\n" + state["kb_ctx"])
    if state.get("tool_research"):
        parts.append("【补充调研】\n" + state["tool_research"])
    return "\n\n".join(parts)


def make_draft_node(ctx: ToolContext, model_pack):
    def run(state: AgentState) -> dict:
        trace = []
        extra = state.get("skill_prompt", "")
        if state.get("review") and not state["review"].get("ok"):
            extra += f"\n【重写警告】上一版被否决：{state['review'].get('reason')}。务必避开同类问题。"
        resp = _invoke(ctx.db, state["user_id"], state["username"], model_pack,
                       [SystemMessage(content=DRAFT_RULES + ("\n" + extra if extra else "")),
                        HumanMessage(content=_context_block(state))], "draft", trace)
        raw = re.sub(r"<think>.*?</think>", "", resp.content or "", flags=re.S).strip()
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        candidates = [re.sub(r"^\d[.、]\s*", "", l) for l in lines] or [raw]
        return {"candidates": candidates[:3], "trace": trace}
    return run


def node_review(ctx: ToolContext, model_pack, enabled: bool = True):
    def run(state: AgentState) -> dict:
        trace = []
        if not enabled:
            trace.append({"node": "review", "detail": "画布已停用质检节点，直接放行", "ms": 0})
            return {"review": {"ok": True, "reason": ""}, "trace": trace}
        taboo = ""
        for chunk in (state.get("persona_ctx") or "").split("---"):
            if "雷区" in chunk or "禁忌" in chunk:
                taboo += chunk
        try:
            resp = _invoke(ctx.db, state["user_id"], state["username"], model_pack,
                           [SystemMessage(content="你是回复质检员。对照【雷区】判断候选回复是否违反雷区、"
                                                  "说教、过度承诺（尤其金钱）、或明显低情商。"
                                                  "只输出 PASS 或 FAIL:原因"),
                            HumanMessage(content=f"【雷区】\n{taboo or '（无特别雷区，仍需检查金钱承诺与说教）'}\n"
                                                 f"【候选回复】\n" + "\n".join(state.get("candidates", [])))],
                           "review", trace)
            verdict = (resp.content or "").strip()
            ok = verdict.upper().startswith("PASS")
        except Exception as e:
            trace.append({"node": "review", "detail": f"质检异常，放行：{str(e)[:150]}", "ms": 0})
            return {"review": {"ok": True, "reason": ""}, "trace": trace}
        trace.append({"node": "review", "detail": verdict[:200], "ms": 0})
        return {"review": {"ok": ok, "reason": "" if ok else verdict[:200]}, "trace": trace}
    return run


def node_bump(ctx: ToolContext, model_pack):
    def run(state: AgentState) -> dict:
        if not state["review"]["ok"]:
            return {"redraft_count": state.get("redraft_count", 0) + 1}
        return {}
    return run


def node_finalize(ctx: ToolContext, model_pack):
    def run(state: AgentState) -> dict:
        cands = []
        for c in state.get("candidates", []):
            c = c.strip().strip('"')
            if c and c not in cands:
                cands.append(c)
        return {"candidates_final": cands[:3]}
    return run


# ---------- 组图与执行 ----------

def build_graph(db, user_id: str, username: str, model_spec: str, person: str,
                history: str, engine: str, temperature: float = 0.8):
    canvas = {n["id"]: n for n in load_canvas()["nodes"]}
    research_cfg = canvas.get("research", {})
    review_cfg = canvas.get("review", {})
    max_redraft = int(review_cfg.get("max_redraft", 1))

    ctx = ToolContext(db=db, user_id=user_id, person=person, trace=[])
    model_pack = resolve_model(db, user_id, model_spec, temperature)
    review_ctx = ToolContext(db=db, user_id=user_id, person=person, trace=[])

    g = StateGraph(AgentState)
    g.add_node("retrieve", node_retrieve(ctx, model_pack))
    g.add_node("research", node_research(ctx, model_pack, int(research_cfg.get("max_steps", 3))))
    g.add_node("draft", make_draft_node(ctx, model_pack))
    g.add_node("redraft", make_draft_node(ctx, model_pack))
    g.add_node("review", node_review(review_ctx, model_pack, enabled=bool(review_cfg.get("enabled", True))))
    g.add_node("bump", node_bump(ctx, model_pack))
    g.add_node("finalize", node_finalize(ctx, model_pack))

    g.set_entry_point("retrieve")
    g.add_conditional_edges(
        "retrieve",
        lambda s: "research" if s["engine"] == "agent" else "draft",
        {"research": "research", "draft": "draft"})
    g.add_edge("research", "draft")
    g.add_edge("draft", "review")
    g.add_edge("redraft", "review")
    g.add_edge("review", "bump")

    g.add_conditional_edges(
        "bump",
        lambda s: ("redraft" if not s["review"]["ok"] and s.get("redraft_count", 0) <= max_redraft else "finalize"),
        {"redraft": "redraft", "finalize": "finalize"})
    g.add_edge("finalize", END)

    return g.compile(), ctx


def run_agent(db, user_id: str, username: str, message: str, person: str,
              history: str, model_spec: str, engine: str = "agent",
              temperature: float = 0.8) -> dict:
    t0 = time.time()
    own_db = db is None
    if own_db:
        from ..database import SessionLocal
        db = SessionLocal()
    try:
        return _run(db, user_id, username, message, person, history,
                    model_spec, engine, temperature, t0)
    finally:
        if own_db:
            db.close()


def _run(db, user_id, username, message, person, history,
         model_spec, engine, temperature, t0) -> dict:
    app, ctx = build_graph(db, user_id, username, model_spec, person, history,
                           engine, temperature)
    state = {
        "message": message, "person": person or "", "history": history or "",
        "user_id": user_id, "username": username,
        "model_spec": model_spec, "temperature": temperature,
        "engine": engine, "redraft_count": 0,
    }
    final = app.invoke(state)
    matched = skills.match_skills(message)
    return {
        "candidates": final.get("candidates_final") or final.get("candidates") or [],
        "sources": [{"kind": "persona", "text": final["persona_ctx"]}
                    if final.get("persona_ctx") else
                    {"kind": "book", "text": final.get("kb_ctx", "")}],
        "trace": final.get("trace", []),
        "errors": final.get("errors", []),
        "engine": engine,
        "skill": matched[0]["name"] if matched else "通用高情商",
        "elapsed_ms": int((time.time() - t0) * 1000),
    }
