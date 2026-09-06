# -*- coding: utf-8 -*-
"""模型中心：用户自配服务商 / 拉取模型 / 连接测试 / 用量统计"""
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import llm_schemas as sc
from ..config import load_settings
from ..database import get_db, new_id, now
from ..models import LlmProvider, LlmUsage
from ..services import cache, llm
from ..services.security import get_current_user

router = APIRouter(prefix="/api/llm", tags=["模型中心"],
                   dependencies=[Depends(get_current_user)])

MODELS_CACHE_TTL = 600  # 拉取模型列表缓存 10 分钟


def _get_provider(db: Session, user_id: str, provider_id: str, allow_builtin: bool = True) -> LlmProvider:
    p = db.get(LlmProvider, provider_id)
    if not p or (p.user_id != user_id and not (allow_builtin and p.user_id == "")):
        raise HTTPException(404, "服务商配置不存在")
    return p


def _dict(p: LlmProvider) -> dict:
    preset = llm.VENDOR_PRESETS.get(p.vendor, {})
    return {
        "id": p.id, "name": p.name, "vendor": p.vendor,
        "vendor_name": preset.get("name", p.vendor),
        "base_url": p.base_url, "enabled": bool(p.enabled),
        "has_key": bool(p.api_key_enc), "docs": preset.get("docs", ""),
        "extra_models": [x for x in (p.extra_models or "").splitlines() if x.strip()],
        "created_at": p.created_at,
    }


@router.get("/presets")
def presets():
    """全部厂商预设（前端新建下拉用）"""
    return [{"code": k, **{kk: vv for kk, vv in v.items()}} for k, v in llm.VENDOR_PRESETS.items()]


@router.get("/providers")
def list_providers(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    builtin = db.scalars(select(LlmProvider).where(LlmProvider.user_id == "")
                         .order_by(LlmProvider.created_at)).all()
    mine = db.scalars(select(LlmProvider).where(LlmProvider.user_id == user["id"])
                      .order_by(LlmProvider.created_at)).all()
    out = []
    for p in [*builtin, *mine]:
        d = _dict(p)
        d["builtin"] = p.user_id == ""
        out.append(d)
    return out


@router.post("/providers")
def create_provider(body: sc.ProviderIn, user: dict = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if body.vendor not in llm.VENDOR_PRESETS:
        raise HTTPException(400, f"未知厂商：{body.vendor}")
    p = LlmProvider(
        id=new_id(), user_id=user["id"], name=body.name.strip(),
        vendor=body.vendor,
        base_url=(body.base_url or llm.VENDOR_PRESETS[body.vendor]["base_url"]).strip(),
        api_key_enc=llm.encrypt_key(body.api_key.strip()),
        enabled=1 if body.enabled else 0,
        extra_models="\n".join(body.extra_models),
        created_at=now(),
    )
    db.add(p)
    db.commit()
    return _dict(p)


@router.put("/{provider_id}")
def update_provider(provider_id: str, body: sc.ProviderUpdate,
                    user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _get_provider(db, user["id"], provider_id, allow_builtin=False)
    if body.name is not None: p.name = body.name.strip()
    if body.base_url is not None: p.base_url = body.base_url.strip()
    if body.api_key is not None: p.api_key_enc = llm.encrypt_key(body.api_key.strip())
    if body.enabled is not None: p.enabled = 1 if body.enabled else 0
    if body.extra_models is not None: p.extra_models = "\n".join(body.extra_models)
    cache.delete_pattern(f"llmmodels:{provider_id}:")
    db.commit()
    return _dict(p)


@router.delete("/{provider_id}")
def delete_provider(provider_id: str, user: dict = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    p = _get_provider(db, user["id"], provider_id, allow_builtin=False)
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.post("/{provider_id}/models")
def fetch_models(provider_id: str, user: dict = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """拉取模型：优先厂商 /models 接口（Redis 缓存 10 分钟），失败回退预设+手动"""
    p = _get_provider(db, user["id"], provider_id, allow_builtin=True)
    key = f"llmmodels:{provider_id}:{hashlib_sha1(p.base_url)}"
    cached = cache.get_json(key)
    if cached:
        return {**cached, "cached": True}

    remote, err = [], ""
    if p.enabled:
        try:
            remote = llm.list_remote_models(p.base_url, llm.decrypt_key(p.api_key_enc))
        except Exception as e:
            err = str(e)[:200]

    preset_models = llm.VENDOR_PRESETS.get(p.vendor, {}).get("models", [])
    manual = [x for x in (p.extra_models or "").splitlines() if x.strip()]
    merged = sorted(set(remote) | set(manual)) if remote else sorted(set(manual) | set(preset_models))
    result = {"models": merged, "remote_count": len(remote), "error": err}
    cache.set_json(key, result, ttl=MODELS_CACHE_TTL)
    return {**result, "cached": False}


def hashlib_sha1(s: str) -> str:
    import hashlib
    return hashlib.sha1(s.encode()).hexdigest()[:10]


@router.post("/{provider_id}/test")
def test_provider(provider_id: str, user: dict = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """连接测试：调一次 models 接口 + 1 token 对话"""
    p = _get_provider(db, user["id"], provider_id)
    api_key = llm.decrypt_key(p.api_key_enc)
    try:
        models = llm.list_remote_models(p.base_url, api_key, timeout=10)
    except Exception as e:
        raise HTTPException(502, f"连接失败：{str(e)[:200]}")
    model = models[0] if models else (llm.VENDOR_PRESETS.get(p.vendor, {}).get("models") or ["test"])[0]
    try:
        content, usage = llm.chat_completion(p.base_url, api_key, model,
                                             "你是测试助手", "回复：OK", temperature=0, timeout=30)
        return {"ok": True, "models_count": len(models), "sample_model": model,
                "latency_ms": usage["latency_ms"]}
    except Exception as e:
        raise HTTPException(502, f"鉴权通过但对话失败：{str(e)[:200]}")


@router.get("/models")
def all_models(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """聚合模型下拉：本地 Ollama + 用户已启用的服务商（对话页选择器用）"""
    out = [{"value": "ollama|qwen3:4b", "label": "本地 Ollama · qwen3:4b",
            "group": "本地 Ollama"}]
    settings = load_settings()
    if settings["chat_model"] and settings["chat_model"] != "qwen3:4b":
        out.append({"value": f"ollama|{settings['chat_model']}",
                    "label": f"本地 Ollama · {settings['chat_model']}", "group": "本地 Ollama"})
    rows = db.scalars(select(LlmProvider).where(
        LlmProvider.user_id.in_([user["id"], ""]), LlmProvider.enabled == 1)).all()
    for p in rows:
        try:
            models = fetch_models_inner(db, user["id"], p)
        except Exception:
            models = []
        for m in models:
            out.append({"value": f"{p.id}|{m}", "label": f"{p.name} · {m}", "group": p.name})
    return out


def fetch_models_inner(db: Session, user_id: str, p: LlmProvider) -> list[str]:
    key = f"llmmodels:{p.id}:{hashlib_sha1(p.base_url)}"
    cached = cache.get_json(key)
    if cached:
        return cached["models"]
    try:
        remote = llm.list_remote_models(p.base_url, llm.decrypt_key(p.api_key_enc), timeout=10)
    except Exception:
        remote = []
    manual = [x for x in (p.extra_models or "").splitlines() if x.strip()]
    preset_models = llm.VENDOR_PRESETS.get(p.vendor, {}).get("models", [])
    models = sorted(set(remote) | set(manual)) if remote else sorted(set(manual) | set(preset_models))
    cache.set_json(key, {"models": models}, ttl=MODELS_CACHE_TTL)
    return models


@router.get("/usage")
def usage(days: int = 7, page: int = 1, size: int = 20, scope: str = "mine",
          user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """模型用量：汇总 + 按模型 + 按天 + 最近调用；scope=all 仅超管（全系统视角）"""
    since = time.time() - days * 86400
    is_all = scope == "all" and user.get("is_superuser")
    q = select(LlmUsage).where(LlmUsage.created_at >= since)
    if not is_all:
        q = q.where(LlmUsage.user_id == user["id"])
    rows = db.scalars(q).all()
    total_calls = len(rows)
    ok_calls = sum(1 for r in rows if r.ok)
    total_tokens = sum(r.total_tokens for r in rows)
    prompt_tokens = sum(r.prompt_tokens for r in rows)
    completion_tokens = sum(r.completion_tokens for r in rows)
    latencies = [r.latency_ms for r in rows if r.ok and r.latency_ms]

    by_model: dict[str, dict] = {}
    by_day: dict[str, dict] = {}
    for r in rows:
        mk = f"{r.vendor}:{r.model}" if r.vendor != "ollama" else r.model
        bm = by_model.setdefault(mk, {"model": mk, "calls": 0, "tokens": 0, "fails": 0})
        bm["calls"] += 1
        bm["tokens"] += r.total_tokens
        bm["fails"] += 0 if r.ok else 1
        day = time.strftime("%m-%d", time.localtime(r.created_at))
        bd = by_day.setdefault(day, {"day": day, "calls": 0, "tokens": 0})
        bd["calls"] += 1
        bd["tokens"] += r.total_tokens

    cnt_q = select(func.count(LlmUsage.id)).where(LlmUsage.created_at >= since)
    recent_q = (select(LlmUsage).where(LlmUsage.created_at >= since)
                .order_by(LlmUsage.id.desc()))
    if not is_all:
        cnt_q = cnt_q.where(LlmUsage.user_id == user["id"])
        recent_q = recent_q.where(LlmUsage.user_id == user["id"])
    total = db.scalar(cnt_q)
    recent_rows = db.scalars(recent_q.offset((page - 1) * size).limit(size)).all()

    return {
        "summary": {
            "calls": total_calls, "ok": ok_calls, "fails": total_calls - ok_calls,
            "total_tokens": total_tokens, "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
        },
        "by_model": sorted(by_model.values(), key=lambda x: -x["calls"]),
        "by_day": [by_day[k] for k in sorted(by_day)],
        "recent": [{"id": r.id, "username": r.username, "vendor": r.vendor, "model": r.model,
                    "kind": r.kind, "total_tokens": r.total_tokens, "latency_ms": r.latency_ms,
                    "ok": bool(r.ok), "error": r.error, "created_at": r.created_at}
                   for r in recent_rows],
        "total": total, "page": page, "size": size, "scope": "all" if is_all else "mine",
    }
