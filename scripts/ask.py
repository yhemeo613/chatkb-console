# -*- coding: utf-8 -*-
"""
检索知识库（个人档案优先 + 书籍知识），生成高情商候选回复

用法：
    # 只看检索到了哪些资料
    python scripts/ask.py "周末有空吗，来我家吃饭" --person 老妈

    # 检索 + 让本地大模型起草 3 个候选回复
    python scripts/ask.py "领导突然在群里表扬我，怎么回" --draft
    python scripts/ask.py "在吗？" --person 示例_同事小王 --draft --model qwen3:4b
"""
import argparse
import re
import sys
from pathlib import Path

import chromadb
import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
DB_DIR = ROOT / "db"
OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "bge-m3"
COLLECTION = "chat_kb"


def embed(text: str):
    r = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": EMBED_MODEL, "input": [text]},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["embeddings"][0]


def fmt_hit(m, doc):
    src = m.get("source", "?")
    extra = []
    if m.get("chapter"):
        extra.append(m["chapter"])
    if m.get("page"):
        extra.append(f"第{m['page']}页")
    loc = f"（{'·'.join(extra)}）" if extra else ""
    tag = "个人档案" if m.get("kind") == "personal" else "书籍"
    return f"[{tag}·{src}{loc}]\n{doc.strip()}"


def retrieve(query: str, person: str, topk: int):
    client = chromadb.PersistentClient(path=str(DB_DIR))
    col = client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
    emb = embed(query)

    hits = {}

    def run(where, n):
        if n <= 0 or col.count() == 0:
            return
        res = col.query(query_embeddings=[emb], n_results=min(n, col.count()), where=where)
        for meta, doc, dist in zip(res["metadatas"][0], res["documents"][0], res["distances"][0]):
            key = meta["source"] + str(meta.get("page", 0))
            if key not in hits or dist < hits[key][1]:
                hits[key] = (fmt_hit(meta, doc), dist, meta.get("kind"))

    run({"kind": "personal"}, 4)
    if person:
        try:
            run({"$and": [{"kind": "personal"}, {"person": person}]}, 3)
        except Exception:
            pass  # 没有该 person 的档案
    run({"kind": "book"}, topk)

    personal = [v[0] for v in sorted(hits.values(), key=lambda x: x[1]) if v[2] == "personal"]
    books = [v[0] for v in sorted(hits.values(), key=lambda x: x[1]) if v[2] == "book"]
    return personal, books


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


def draft(message: str, person: str, history: str, personal, books, model: str):
    parts = [f"【对方消息】\n{message}"]
    if person:
        parts.append(f"【对方是谁】{person}")
    if history:
        parts.append(f"【之前的聊天】\n{history}")
    if personal:
        parts.append("【个人档案】\n" + "\n\n".join(personal))
    if books:
        parts.append("【沟通知识】\n" + "\n\n".join(books))
    parts.append("/no_think")

    r = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_RULES},
                {"role": "user", "content": "\n\n".join(parts)},
            ],
            "stream": False,
            "options": {"temperature": 0.8},
        },
        timeout=600,
    )
    r.raise_for_status()
    content = r.json()["message"]["content"]
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
    return content


def main():
    ap = argparse.ArgumentParser(description="聊天知识库检索 + 高情商回复起草")
    ap.add_argument("message", help="对方发来的消息")
    ap.add_argument("--person", default="", help="对方称呼/名字（配合关系档案）")
    ap.add_argument("--history", default="", help="之前的聊天内容或背景，可选")
    ap.add_argument("--draft", action="store_true", help="调用本地大模型生成候选回复")
    ap.add_argument("--model", default="qwen3:4b", help="本地大模型名（默认 qwen3:4b）")
    ap.add_argument("--topk", type=int, default=6, help="书籍知识检索条数")
    args = ap.parse_args()

    personal, books = retrieve(args.message, args.person, args.topk)

    if not args.draft:
        print("=" * 50)
        print("【个人档案】检索结果")
        for p in personal:
            print("-" * 50)
            print(p)
        print("=" * 50)
        print("【沟通知识】检索结果")
        for b in books:
            print("-" * 50)
            print(b)
        return

    print("正在生成候选回复…\n")
    reply = draft(args.message, args.person, args.history, personal, books, args.model)
    print(reply)
    print()
    if not personal and not books:
        print("（提示：本次没有检索到相关资料，回复仅供参考。先往 personal/ 和 knowledge/ 放内容并重新 ingest）")


if __name__ == "__main__":
    main()
