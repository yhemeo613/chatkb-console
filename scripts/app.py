# -*- coding: utf-8 -*-
"""
聊天知识库本地 Web 界面

    python scripts/app.py
    打开 http://127.0.0.1:8787
"""
import re
import sys
import threading
from pathlib import Path

import requests
from flask import Flask, jsonify, request

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ask  # noqa: E402
import ingest  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OLLAMA_URL = "http://localhost:11434"

app = Flask(__name__)
ingest_state = {"running": False, "done_at": ""}


def list_persons():
    persons = []
    personal_dir = ROOT / "personal"
    if personal_dir.exists():
        for f in sorted(personal_dir.glob("*.md")):
            p = ingest.parse_person(f.read_text(encoding="utf-8", errors="ignore"))
            if p:
                persons.append(p)
    return persons


def list_files():
    out = []
    for name, folder in (("personal", "personal"), ("knowledge", "knowledge")):
        d = ROOT / folder
        if d.exists():
            out += [{"kind": name, "file": f.name} for f in sorted(d.iterdir()) if f.is_file()]
    return out


def ollama_models():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


@app.get("/")
def index():
    return (ROOT / "scripts" / "index.html").read_text(encoding="utf-8")


@app.get("/api/status")
def status():
    import chromadb
    try:
        col = chromadb.PersistentClient(path=str(ingest.DB_DIR)).get_or_create_collection(
            ingest.COLLECTION, metadata={"hnsw:space": "cosine"})
        n = col.count()
    except Exception:
        n = 0
    return jsonify({
        "persons": list_persons(),
        "files": list_files(),
        "models": ollama_models(),
        "chunks": n,
        "ingest_running": ingest_state["running"],
    })


@app.post("/api/ask")
def api_ask():
    data = request.get_json(force=True)
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "消息不能为空"}), 400
    person = (data.get("person") or "").strip()
    history = (data.get("history") or "").strip()
    model = (data.get("model") or "qwen3:4b").strip()
    do_draft = bool(data.get("draft"))

    personal, books = ask.retrieve(message, person, topk=6)
    reply = ""
    if do_draft:
        reply = ask.draft(message, person, history, personal, books, model)
    return jsonify({"personal": personal, "books": books, "reply": reply})


@app.post("/api/ingest")
def api_ingest():
    if ingest_state["running"]:
        return jsonify({"ok": False, "error": "入库正在进行中"}), 409

    def run():
        ingest_state["running"] = True
        try:
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ingest.main()
            ingest_state["log"] = buf.getvalue()
            import datetime
            ingest_state["done_at"] = datetime.datetime.now().strftime("%H:%M:%S")
        except Exception as e:
            ingest_state["log"] = f"入库失败：{e}"
        finally:
            ingest_state["running"] = False

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"ok": True})


@app.get("/api/ingestlog")
def ingestlog():
    return ingest_state.get("log", "入库完成")


if __name__ == "__main__":
    print("聊天知识库界面：http://127.0.0.1:8787  （Ctrl+C 退出）")
    app.run(host="127.0.0.1", port=8787, threaded=True)
