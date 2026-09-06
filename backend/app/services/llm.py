# -*- coding: utf-8 -*-
"""
大模型统一接入层。

协议结论（2025 调研，详见 README「模型服务商兼容表」）：
国内主流厂商全部兼容 OpenAI Chat Completions 协议，仅 base_url 不同——
DeepSeek / Kimi / 智谱 / 通义百炼 / 豆包火山方舟 / 百度千帆v2 / 讯飞星火 /
腾讯混元 / 硅基流动 / MiniMax / 阶跃星辰 / 零一万物 / OpenAI。
本地 Ollama 同样暴露 /v1 OpenAI 兼容端点，因此统一走一套适配器。

模型寻址格式："provider_id|model"；本地默认 "ollama|模型名"。
"""
import base64
import hashlib
import time
from pathlib import Path

import requests
from cryptography.fernet import Fernet, InvalidToken

from ..config import OLLAMA_URL, load_settings
from ..models import LlmUsage

# 厂商预设：默认 base_url + 官方文档 + 常见模型（拉取失败时兜底展示）
VENDOR_PRESETS = {
    "ollama":      {"name": "本地 Ollama", "base_url": f"{OLLAMA_URL}/v1",
                    "docs": "https://ollama.com", "models": []},
    "deepseek":    {"name": "DeepSeek 深度求索", "base_url": "https://api.deepseek.com/v1",
                    "docs": "https://api-docs.deepseek.com/zh-cn/",
                    "models": ["deepseek-chat", "deepseek-reasoner"]},
    "moonshot":    {"name": "Kimi 月之暗面", "base_url": "https://api.moonshot.cn/v1",
                    "docs": "https://platform.kimi.ai/docs/api/overview",
                    "models": ["kimi-k2-0905-preview", "moonshot-v1-8k", "moonshot-v1-32k"]},
    "zhipu":       {"name": "智谱 GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4",
                    "docs": "https://docs.bigmodel.cn/cn/guide/develop/openai/introduction",
                    "models": ["glm-4-plus", "glm-4-air", "glm-4-flash"]},
    "qwen":        {"name": "通义千问（阿里云百炼）", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    "docs": "https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope",
                    "models": ["qwen-max", "qwen-plus", "qwen-turbo"]},
    "doubao":      {"name": "豆包（火山方舟）", "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                    "docs": "https://www.volcengine.com/docs/82379/1330626",
                    "models": ["doubao-pro-32k", "doubao-lite-32k"]},
    "qianfan":     {"name": "百度千帆", "base_url": "https://qianfan.baidubce.com/v2",
                    "docs": "https://cloud.baidu.com/doc/qianfan/s/Hmh4suq26",
                    "models": ["ernie-4.0-turbo-8k", "ernie-3.5-8k", "deepseek-v3"]},
    "spark":       {"name": "讯飞星火", "base_url": "https://spark-api-open.xf-yun.com/v1",
                    "docs": "https://www.xfyun.cn/doc/spark/HTTP%E8%B0%83%E7%94%A8%E6%96%87%E6%A1%A3.html",
                    "models": ["generalv3.5", "4.0Ultra", "generalv3"]},
    "hunyuan":     {"name": "腾讯混元", "base_url": "https://api.hunyuan.cloud.tencent.com/v1",
                    "docs": "https://cloud.tencent.com/document/product/1729/111007",
                    "models": ["hunyuan-turbos-latest", "hunyuan-lite", "hunyuan-standard"]},
    "siliconflow": {"name": "硅基流动 SiliconFlow", "base_url": "https://api.siliconflow.cn/v1",
                    "docs": "https://docs.siliconflow.cn/cn/userguide/quickstart",
                    "models": ["deepseek-ai/DeepSeek-V3", "Qwen/Qwen2.5-72B-Instruct",
                               "Pro/Qwen/Qwen2.5-7B-Instruct"]},
    "minimax":     {"name": "MiniMax", "base_url": "https://api.minimaxi.com/v1",
                    "docs": "https://platform.minimax.io/docs/api-reference/text-openai-api",
                    "models": ["abab6.5s-chat", "MiniMax-Text-01"]},
    "step":        {"name": "阶跃星辰", "base_url": "https://api.stepfun.com/v1",
                    "docs": "https://platform.stepfun.com/docs/zh/guides/developer/openai",
                    "models": ["step-2-16k", "step-1-8k"]},
    "yi":          {"name": "零一万物", "base_url": "https://api.lingyiwanwu.com/v1",
                    "docs": "https://platform.lingyiwanwu.com/docs",
                    "models": ["yi-lightning", "yi-large"]},
    "openai":      {"name": "OpenAI（国际）", "base_url": "https://api.openai.com/v1",
                    "docs": "https://platform.openai.com/docs",
                    "models": ["gpt-4o-mini", "gpt-4o"]},
    "custom":      {"name": "自定义（OpenAI 兼容）", "base_url": "",
                    "docs": "", "models": []},
}


# ---------- API Key 加密（密钥由 settings.json 的 jwt_secret 派生） ----------

def _fernet():
    secret = load_settings()["jwt_secret"]
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt_key(api_key: str) -> str:
    if not api_key:
        return ""
    return _fernet().encrypt(api_key.encode()).decode()


def decrypt_key(enc: str) -> str:
    if not enc:
        return ""
    try:
        return _fernet().decrypt(enc.encode()).decode()
    except InvalidToken:
        return ""


# ---------- OpenAI 兼容调用 ----------

def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"} if api_key else \
           {"Content-Type": "application/json"}


def list_remote_models(base_url: str, api_key: str, timeout: int = 15) -> list[str]:
    """GET {base_url}/models（OpenAI 兼容）；失败抛异常由上层兜底为预设模型"""
    base = base_url.rstrip("/")
    r = requests.get(f"{base}/models", headers=_headers(api_key), timeout=timeout)
    r.raise_for_status()
    data = r.json().get("data", [])
    return sorted({m.get("id") for m in data if m.get("id")})


def chat_completion(base_url: str, api_key: str, model: str, system: str, user: str,
                    temperature: float = 0.8, timeout: int = 300,
                    no_think: bool = False) -> tuple[str, dict]:
    """POST /chat/completions，返回 (回复文本, usage字段)；no_think 仅对 Qwen 系本地模型有意义"""
    base = base_url.rstrip("/")
    t0 = time.time()
    r = requests.post(
        f"{base}/chat/completions",
        headers=_headers(api_key),
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user + ("\n/no_think" if no_think else "")},
            ],
            "temperature": temperature,
            "stream": False,
        },
        timeout=timeout,
    )
    latency_ms = int((time.time() - t0) * 1000)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    content = data["choices"][0]["message"]["content"] or ""
    u = data.get("usage") or {}
    usage = {
        "prompt_tokens": int(u.get("prompt_tokens") or 0),
        "completion_tokens": int(u.get("completion_tokens") or 0),
        "total_tokens": int(u.get("total_tokens") or 0),
        "latency_ms": latency_ms,
    }
    return content, usage


def record_usage(db, user_id: str, vendor: str, provider_id: str, model: str,
                 kind: str, usage: dict | None = None, ok: bool = True, error: str = "",
                 username: str = ""):
    """每次模型调用落一条流水（含本地 Ollama），供用量统计"""
    u = usage or {}
    db.add(LlmUsage(
        user_id=user_id, username=username, vendor=vendor, provider_id=provider_id,
        model=model, kind=kind,
        prompt_tokens=u.get("prompt_tokens", 0), completion_tokens=u.get("completion_tokens", 0),
        total_tokens=u.get("total_tokens", 0), latency_ms=u.get("latency_ms", 0),
        ok=1 if ok else 0, error=error[:500], created_at=time.time(),
    ))
    db.commit()
