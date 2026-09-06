# -*- coding: utf-8 -*-
"""高情商回复生成：个人档案 + 知识库检索 -> 本地 Ollama 或云端大模型（统一用量记录）"""
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import schemas
from ..config import OLLAMA_URL, load_settings
from ..database import get_db
from ..models import LlmProvider
from ..services import cache, embeddings, llm, vectorstore
from ..services.security import get_current_user

router = APIRouter(prefix="/api/chat", tags=["回复生成"], dependencies=[Depends(get_current_user)])

SYSTEM_RULES = """你是用户的微信高情商回复助手。根据提供的资料和对话上下文，用用户的口吻生成 3 个候选回复：
1. 稳妥得体版
2. 幽默拉近距离版
3. 简短直接版

要求：
- 每条只输出回复本身，以"1.""2.""3."开头，不要解释、不要客套前言
- 资料中的【雷区/禁忌】绝对不能碰
- 涉及具体的人和事时优先参考【个人档案】
- 沟通技巧参考【沟通知识】，但不要生搬硬套
- 像正常人发微信，口语化，别用书面语，长度一般不超过两三句话"""


def rate_limit(request: Request):
    """Redis 滑动窗口限流：每 IP 每分钟 N 次（N 来自系统设置）"""
    ip = request.client.host if request.client else "unknown"
    limit = int(load_settings()["rate_limit_per_min"])
    count = cache.incr_with_ttl(f"rl:chat:{ip}", 60)
    if count > limit:
        raise HTTPException(429, f"请求太频繁，每分钟最多 {limit} 次，请稍后再试")


def _retrieve(db: Session, kb_type: str, query: str, n: int) -> list[dict]:
    out = []
    from ..models import KnowledgeBase
    for kb in db.query(KnowledgeBase).filter(KnowledgeBase.type == kb_type):
        emb = embeddings.embed_one(query, kb.embed_model)
        out += vectorstore.query(kb.id, emb, n)
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:n]


def _hit_source(h: dict) -> dict:
    return {
        "kind": h.get("kb_type", "docs"),
        "kb_name": h.get("kb_name", ""),
        "source": h["metadata"].get("source", ""),
        "chapter": h["metadata"].get("chapter", ""),
        "page": h["metadata"].get("page", 0),
        "score": h["score"],
        "text": h["text"],
    }


def _call_model(db: Session, user_id: str, username: str, model_spec: str,
                prompt: str, temperature: float) -> str:
    """按 'provider_id|model' 寻址调用；'ollama|xxx' 或裸模型名走本地。统一记录用量。"""
    settings = load_settings()
    if "|" in model_spec:
        provider_id, model = model_spec.split("|", 1)
    else:
        provider_id, model = "ollama", model_spec or settings["chat_model"]

    if provider_id == "ollama":
        try:
            content, usage = llm.chat_completion(
                f"{OLLAMA_URL}/v1", "", model, SYSTEM_RULES, prompt, temperature, no_think=True)
            llm.record_usage(db, user_id, "ollama", "", model, "chat", usage, username=username)
            return content
        except Exception as e:
            llm.record_usage(db, user_id, "ollama", "", model, "chat", None, ok=False, error=str(e), username=username)
            raise HTTPException(502, f"本地模型调用失败（确认 Ollama 已启动）：{e}")

    p = db.get(LlmProvider, provider_id)
    if not p or (p.user_id != user_id and p.user_id != ""):
        raise HTTPException(404, "模型服务商配置不存在")
    if not p.enabled:
        raise HTTPException(400, f"服务商「{p.name}」已被停用")
    try:
        content, usage = llm.chat_completion(
            p.base_url, llm.decrypt_key(p.api_key_enc), model,
            SYSTEM_RULES, prompt, temperature, no_think=(p.vendor == "ollama"))
        llm.record_usage(db, user_id, p.vendor, p.id, model, "chat", usage, username=username)
        return content
    except HTTPException:
        raise
    except Exception as e:
        llm.record_usage(db, user_id, p.vendor, p.id, model, "chat", None, ok=False, error=str(e), username=username)
        raise HTTPException(502, f"「{p.name}」调用失败：{str(e)[:200]}")


@router.post("/reply", dependencies=[Depends(rate_limit)])
def reply(body: schemas.ReplyIn, db: Session = Depends(get_db),
          user: dict = Depends(get_current_user)):
    settings = load_settings()
    model_spec = body.model or settings["chat_model"]
    top_k = body.top_k or settings["top_k"]
    temperature = body.temperature if body.temperature is not None else settings["temperature"]

    personal_hits = _retrieve(db, "persona", body.message, 4)
    book_hits = _retrieve(db, "docs", body.message, top_k)

    parts = [f"【对方消息】\n{body.message}"]
    if body.person:
        parts.append(f"【对方是谁】{body.person}")
    if body.history:
        parts.append(f"【之前的聊天】\n{body.history}")
    if personal_hits:
        parts.append("【个人档案】\n" + "\n\n".join(h["text"] for h in personal_hits))
    if book_hits:
        parts.append("【沟通知识】\n" + "\n\n".join(h["text"] for h in book_hits))

    raw = _call_model(db, user["id"], user["username"], model_spec, "\n\n".join(parts), temperature)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    candidates = [re.sub(r"^\d[.、]\s*", "", l) for l in lines]
    if not candidates:
        candidates = [raw]

    return {
        "candidates": candidates,
        "sources": [_hit_source(h) for h in personal_hits + book_hits],
        "model": model_spec,
    }
