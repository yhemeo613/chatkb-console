# -*- coding: utf-8 -*-
"""
工作流执行器：把编排画布（Dify 风格节点图）解释执行。

节点类型（全部真实作用于回复生成）：
  start               开始：装配上下文（消息/人物/历史）
  knowledge_retrieve  知识检索：个人档案 + 书籍知识（config.top_k）
  tool_research       工具研究：ReAct 循环调用工具（config.max_steps, config.tools）
  llm                 LLM 节点：渲染提示词模板 {{message}}/{{knowledge}}/...，
                      输出写入 config.output（默认 candidates，自动解析 1.2.3. 编号）
  review              质检门控：按 config.checklist 判定 PASS/FAIL，
                      PASS 走 pass 边、FAIL 走 fail 边（无 fail 边直接放行）
  answer              输出：清洗候选并结束

画布 JSON（v2）：nodes[{id,type,x,y,config}], edges[{source,target,label?}]
label: 条件分支标记（pass/fail）。循环（如 review-FAIL→重写 LLM）由
review.config.max_redraft 限制回边次数，防止死循环。
"""
import json
import re
import time
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from . import skills
from .tools.builtin import ToolContext, build_tools
from .plugins import build_plugin_tools
from . import mcp_client
from ..config import OLLAMA_URL, load_settings
from ..models import LlmProvider
from ..services import embeddings, llm, vectorstore
from ..database import SessionLocal
from langchain_openai import ChatOpenAI

DEFAULT_TEMPLATE = {
    "version": 2,
    "nodes": [
        {"id": "start", "type": "start", "x": 40, "y": 180, "config": {}},
        {"id": "retrieve", "type": "knowledge_retrieve", "x": 260, "y": 180,
         "config": {"top_k": 4}},
        {"id": "research", "type": "tool_research", "x": 480, "y": 60,
         "config": {"max_steps": 3, "tools": ["kb_search", "relationship_profile", "history_recall"]}},
        {"id": "draft", "type": "llm", "x": 700, "y": 180,
         "config": {"title": "起草回复",
                    "system": "你是用户的微信高情商回复助手。结合资料用用户口吻生成 3 个候选回复，"
                              "以 1. 2. 3. 编号，口语化短句，不踩雷区。",
                    "prompt": "【对方消息】{{message}}\n【对方是谁】{{person}}\n【历史】{{history}}\n"
                              "【个人档案】{{knowledge}}\n【沟通知识】{{docs}}\n【补充调研】{{research}}",
                    "output": "candidates"}},
        {"id": "review", "type": "review", "x": 920, "y": 60,
         "config": {"checklist": "对照【雷区】检查是否违反禁忌、说教、过度承诺金钱；只输出 PASS 或 FAIL:原因",
                    "max_redraft": 1}},
        {"id": "redraft", "type": "llm", "x": 920, "y": 300,
         "config": {"title": "重写（质检否决后）",
                    "system": "上一版候选被质检否决。原因：{{fail_reason}}。重新生成 3 个候选，务必避开问题。"
                              "以 1. 2. 3. 编号。",
                    "prompt": "【对方消息】{{message}}\n【个人档案】{{knowledge}}\n【被否决版本】{{candidates}}",
                    "output": "candidates"}},
        {"id": "answer", "type": "answer", "x": 1140, "y": 180, "config": {}},
    ],
    "edges": [
        {"source": "start", "target": "retrieve"},
        {"source": "retrieve", "target": "research"},
        {"source": "retrieve", "target": "draft"},
        {"source": "research", "target": "draft"},
        {"source": "draft", "target": "review"},
        {"source": "review", "target": "answer", "label": "pass"},
        {"source": "review", "target": "redraft", "label": "fail"},
        {"source": "redraft", "target": "review", "label": "recheck"},
    ],
}


def load_flow_template() -> dict:
    """读取画布；v1 旧格式（无 version）自动升级为默认 v2 模板"""
    from ..config import DATA_DIR
    f = Path(DATA_DIR) / "agent_canvas.json"
    if f.exists():
        try:
            cfg = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(cfg, dict) and cfg.get("version") == 2 and cfg.get("nodes"):
                return cfg
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_TEMPLATE))


def save_flow_template(cfg: dict):
    from ..config import DATA_DIR
    f = Path(DATA_DIR) / "agent_canvas.json"
    f.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- 候选解析（过滤思考型模型的元语言行） ----------

META_LINE = re.compile(r"^(【|\[?检查|重新生成|候选\d|基于|说明|注意|分析|\*\*|好嘞，这|思路)")


def parse_candidates(raw: str) -> list:
    """从模型输出提取候选：优先编号行；过滤【检查】/重新生成等元语言；最多 3 条"""
    lines = [l.strip() for l in (raw or "").splitlines() if l.strip()]
    lines = [l for l in lines if not META_LINE.match(l) and len(l) >= 3]
    numbered = [re.sub(r"^\d[.、）)]\s*", "", l) for l in lines if re.match(r"^\d[.、）)]", l)]
    if len(numbered) >= 2:
        return numbered[:3]
    plain = [l for l in lines]
    return plain[:3]


# ---------- 变量渲染 ----------

VAR_RE = re.compile(r"\{\{(\w+)\}\}")


class EmitList(list):
    """trace 列表：每次 append 自动回调 emit，驱动 SSE 实时推送"""

    def __init__(self, emit=None):
        super().__init__()
        self._emit = emit

    def append(self, item):
        super().append(item)
        if self._emit:
            try:
                self._emit({"type": "trace", **item})
            except Exception:
                pass


def render(template: str, ctx: dict) -> str:
    def sub(m):
        v = ctx.get(m.group(1), "")
        if isinstance(v, list):
            return "\n".join(str(x) for x in v)
        return str(v)
    return VAR_RE.sub(sub, template or "")


# ---------- 模型 ----------

def resolve_model(db, user_id: str, model_spec: str, temperature: float):
    settings = load_settings()
    if "|" in model_spec:
        provider_id, model = model_spec.split("|", 1)
    else:
        provider_id, model = "ollama", model_spec or settings["chat_model"]
    if provider_id == "ollama":
        return (ChatOpenAI(model=model, base_url=f"{OLLAMA_URL}/v1", api_key="ollama",
                           temperature=temperature, timeout=600), "ollama", "")
    p = db.get(LlmProvider, provider_id)
    if not p or p.user_id not in (user_id, ""):
        raise ValueError(f"模型服务商 {provider_id} 不存在")
    if not p.enabled:
        raise ValueError(f"服务商「{p.name}」已停用")
    return (ChatOpenAI(model=model, base_url=p.base_url,
                       api_key=llm.decrypt_key(p.api_key_enc) or "none",
                       temperature=temperature, timeout=300), p.vendor, p.id)


# ---------- 执行器 ----------

def run_flow(db, user_id: str, username: str, message: str, person: str,
             history: str, model_spec: str, engine: str = "agent",
             temperature: float = 0.8, emit=None) -> dict:
    t0 = time.time()
    own = db is None
    if own:
        db = SessionLocal()
    try:
        return _execute(db, user_id, username, message, person, history,
                        model_spec, engine, temperature, t0, emit)
    finally:
        if own:
            db.close()


def _execute(db, user_id, username, message, person, history,
             model_spec, engine, temperature, t0, emit=None) -> dict:
    template = load_flow_template()
    nodes = {n["id"]: n for n in template["nodes"]}
    edges = template["edges"]
    start = next((n for n in template["nodes"] if n["type"] == "start"), None)
    if not start:
        raise ValueError("画布缺少「开始」节点")
    model_pack = resolve_model(db, user_id, model_spec, temperature)
    trace = EmitList(emit)
    errors: list[str] = []

    ctx: dict[str, Any] = {
        "message": message, "person": person or "", "history": history or "",
        "knowledge": "", "docs": "", "research": "", "candidates": "",
        "fail_reason": "", "verdict": "",
    }
    tool_ctx = ToolContext(db=db, user_id=user_id, person=person or "", history=history or "", trace=trace)
    visits: dict[str, int] = {}
    current = start
    candidates: list[str] = []
    skill_hit = skills.match_skills(message)

    while current is not None:
        nid, ntype, cfg = current["id"], current["type"], current.get("config") or {}
        visits[nid] = visits.get(nid, 0) + 1
        if visits[nid] > 12:
            trace.append({"node": nid, "detail": "超出节点执行上限，强制结束", "ms": 0})
            break
        t1 = time.time()

        if ntype == "start":
            trace.append({"node": nid, "detail": "开始：装配上下文", "ms": 0})

        elif ntype == "knowledge_retrieve":
            top_k = int(cfg.get("top_k", 4))
            knowledge, docs = [], []
            from ..models import KnowledgeBase
            for kb in db.query(KnowledgeBase):
                emb = embeddings.embed_one(message, kb.embed_model)
                for h in vectorstore.query(kb.id, emb, top_k):
                    line = f"[{h['metadata'].get('source', '')}]\n{h['text']}"
                    (knowledge if kb.type == "persona" else docs).append(line)
            ctx["knowledge"] = "\n\n".join(knowledge[:4])
            ctx["docs"] = "\n\n".join(docs[:6])
            trace.append({"node": nid, "detail": f"档案 {len(knowledge)} 段 / 知识 {len(docs)} 段",
                          "ms": int((time.time() - t1) * 1000)})

        elif ntype == "tool_research":
            if engine == "fast":
                trace.append({"node": nid, "detail": "快速引擎：跳过工具研究", "ms": 0})
                outs = [e for e in edges if e["source"] == nid]
                current = nodes[outs[0]["target"]] if outs else None
                continue
            wanted = set(cfg.get("tools") or [])
            all_tools = build_tools(tool_ctx, extra_tools=build_plugin_tools() + mcp_client.build_mcp_tools())
            tools = [t for t in all_tools if not wanted or t.name in wanted] or all_tools
            collected = []
            try:
                researcher = model_pack[0].bind_tools(tools)
            except Exception:
                researcher = model_pack[0]
            tool_map = {t.name: t for t in tools}
            msgs = [SystemMessage(content="你是回复研究员，用工具收集情报（最多 3 轮）后输出要点。"),
                    HumanMessage(content=f"对方「{person or '未知'}」说：{message}")]
            for step in range(1, int(cfg.get("max_steps", 3)) + 1):
                resp = researcher.invoke(msgs)
                calls = getattr(resp, "tool_calls", None) or []
                if not calls:
                    collected.append(str(resp.content)[:800])
                    break
                msgs.append(resp)
                for call in calls:
                    tool = tool_map.get(call["name"])
                    try:
                        result = tool.invoke(call.get("args") or {}) if tool else "未知工具"
                    except Exception as e:
                        result = f"工具失败：{e}"
                    trace.append({"node": nid, "tool": call["name"],
                                  "detail": json.dumps(call.get("args", {}), ensure_ascii=False)[:250]
                                            + " → " + str(result)[:150],
                                  "ms": int((time.time() - t1) * 1000)})
                    msgs.append(ToolMessage(content=str(result)[:2000],
                                            tool_call_id=call.get("id") or call["name"]))
                    collected.append(f"[{call['name']}] {str(result)[:400]}")
            ctx["research"] = "\n".join(collected)[:3000]

        elif ntype == "llm":
            system = render(cfg.get("system", ""), ctx)
            user_prompt = render(cfg.get("prompt", ""), ctx)
            if not system and cfg.get("title"):
                system = cfg["title"]
            trace.append({"node": nid, "detail": f"LLM 渲染提示词（{len(user_prompt)} 字）", "ms": 0})
            t2 = time.time()
            out_var = cfg.get("output", "candidates")
            raw = ""
            if emit and out_var == "candidates":
                # 流式：候选逐 token 推送到前端实时渲染
                full = ""
                for chunk in model_pack[0].stream([SystemMessage(content=system),
                                                   HumanMessage(content=user_prompt)]):
                    delta = chunk.content or ""
                    if delta:
                        full += delta
                        emit({"type": "token", "delta": delta})
                raw = re.sub(r"<think>.*?</think>", "", full, flags=re.S).strip()
                usage = {"prompt_tokens": 0, "completion_tokens": 0,
                         "total_tokens": max(1, int(len(full) / 2)),   # 流式无精确 usage，按字符近似
                         "latency_ms": int((time.time() - t2) * 1000)}
            else:
                resp = model_pack[0].invoke([SystemMessage(content=system),
                                             HumanMessage(content=user_prompt)])
                meta = getattr(resp, "usage_metadata", None) or {}
                usage = {"prompt_tokens": meta.get("input_tokens", 0),
                         "completion_tokens": meta.get("output_tokens", 0),
                         "total_tokens": meta.get("total_tokens", 0),
                         "latency_ms": int((time.time() - t2) * 1000)}
                raw = re.sub(r"<think>.*?</think>", "", resp.content or "", flags=re.S).strip()
            llm.record_usage(db, user_id, model_pack[1], model_pack[2],
                             getattr(model_pack[0], "model_name", "llm"), "chat",
                             usage, username=username)
            if out_var == "candidates":
                cands = parse_candidates(raw)
                ctx["candidates"] = "\n".join(cands) or raw
                candidates = cands or [raw]
                trace.append({"node": nid, "detail": f"生成 {len(candidates)} 个候选", "ms": usage["latency_ms"]})
            else:
                ctx[out_var] = raw
                trace.append({"node": nid, "detail": f"输出写入 {out_var}（{len(raw)} 字）", "ms": usage["latency_ms"]})

        elif ntype == "review":
            checklist = render(cfg.get("checklist", ""), ctx) or "检查金钱承诺、说教、违反雷区"
            t2 = time.time()
            resp = model_pack[0].invoke([
                SystemMessage(content="你是质检员。按检查清单判断候选回复，只输出 PASS 或 FAIL:原因"),
                HumanMessage(content=f"【检查清单】{checklist}\n【候选】\n{ctx.get('candidates', '')}")])
            meta = getattr(resp, "usage_metadata", None) or {}
            llm.record_usage(db, user_id, model_pack[1], model_pack[2],
                             getattr(model_pack[0], "model_name", "review"), "chat",
                             {"prompt_tokens": meta.get("input_tokens", 0),
                              "completion_tokens": meta.get("output_tokens", 0),
                              "total_tokens": meta.get("total_tokens", 0),
                              "latency_ms": int((time.time() - t2) * 1000)}, username=username)
            verdict = re.sub(r"<think>.*?</think>", "", (resp.content or ""), flags=re.S).strip()
            ok = verdict.upper().startswith("PASS")
            ctx["verdict"] = verdict[:200]
            ctx["fail_reason"] = "" if ok else verdict[:300]
            trace.append({"node": nid, "detail": verdict[:200], "ms": int((time.time() - t2) * 1000)})

        elif ntype == "answer":
            raw = ctx.get("candidates", "")
            lines = [l.strip() for l in raw.splitlines() if l.strip()] if raw else []
            candidates = [re.sub(r"^\d[.、]\s*", "", l) for l in lines] or ([raw] if raw else [])
            trace.append({"node": nid, "detail": f"输出 {len(candidates)} 个候选", "ms": 0})
            current = None
            break

        else:
            trace.append({"node": nid, "detail": f"未知节点类型 {ntype}，跳过", "ms": 0})

        # 走边：条件节点按 verdict，其余走第一条（或唯一）出边
        outs = [e for e in edges if e["source"] == nid]
        if not outs:
            break
        nxt = None
        if ntype == "review":
            want = "pass" if ctx.get("verdict", "").upper().startswith("PASS") else "fail"
            nxt = next((e for e in outs if e.get("label") == want), None)
            if nxt is None and want == "fail":
                nxt = next((e for e in outs if e.get("label") == "pass"), None)
        current = nodes[(nxt or outs[0])["target"]]

    matched = skills.match_skills(message)
    return {
        "candidates": candidates,
        "sources": [{"kind": "persona", "text": ctx.get("knowledge", "")},
                    {"kind": "book", "text": ctx.get("docs", "")}],
        "trace": trace,
        "errors": errors,
        "engine": "flow",
        "skill": matched[0]["name"] if matched else "通用高情商",
        "elapsed_ms": int((time.time() - t0) * 1000),
    }
