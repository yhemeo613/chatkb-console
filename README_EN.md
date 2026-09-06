# ChatKB Console

English | [简体中文](./README.md)

A local-first "high-EQ WeChat reply" agent system: books + personal profiles are fully vectorized; retrieval and generation can run entirely on your machine or hook into any major Chinese LLM vendor. LangGraph-style workflow orchestration + skills/plugins/MCP extensions + a complete RBAC admin console.

![Dashboard](docs/screenshots/dashboard.png)

## ✨ Features

| Module | Highlights |
|---|---|
| 💬 Reply Chat | WeChat-style conversation UI; multi-step agent (retrieve → tool research → draft → taboo review gate) with **live streaming of the reasoning chain**; click a candidate to copy |
| 📚 Knowledge Base | Multiple KBs, drag-drop upload (PDF/EPUB/DOCX/TXT/MD/HTML), chunking → bge-m3 embeddings → Chroma; live ingestion progress over WebSocket |
| 🔍 Semantic Search | Cross-KB retrieval with relevance scores, source (chapter/page), keyword highlighting (Redis-cached) |
| 🤖 LLM Center | Unified OpenAI-compatible access to 14+ Chinese vendors (DeepSeek, Kimi, Zhipu, Qwen, Doubao, Qianfan, Spark, Hunyuan, SiliconFlow, MiniMax, StepFun, Yi, OpenAI, custom). Pick vendor + paste key, that's it. Model listing, connectivity test, token usage analytics (trend chart & model distribution donut) |
| 🧩 Extension Center | SQLite browser (tables + read-only SQL console), Redis browser (scan/view/TTL), skill manager (hot-reload JSON), HTTP tool plugins, MCP integration (stdio/SSE) |
| 🎨 Orchestration Canvas | Dify-style workflow editor: 6 node types, drag-to-connect, per-node config (prompt templates with `{{variables}}`), conditional branches, test-run. **The canvas definition actually drives the execution engine** |
| 👥 Admin | RBAC (users-roles-menus/button permission codes), open registration, audit log |
| 📈 Ops | Ollama/Redis/SQLite/Chroma health & sizes, task center, audit trail |

![Reply with live trace](docs/screenshots/reply.png)
![Canvas](docs/screenshots/canvas.png)

## 🏗️ Tech Stack

- **Frontend**: Vue 3 · Vite · Ant Design Vue · Pinia · Vue Router · Axios · ECharts · Vue Flow · Less
- **Backend**: FastAPI · SQLAlchemy 2.0 (SQLite/WAL) · Pydantic v2 · JWT (PyJWT + PBKDF2) · Redis (embedding cache / rate limiting / task state / pub-sub, auto-fallback to fakeredis) · WebSocket · APScheduler · Chroma · Ollama · LangChain/LangGraph
- **Agent**: workflow interpreter (`agent/flow.py`), 4 built-in tools, hot-reloadable skills, HTTP plugins, MCP client, NDJSON streaming
- **Tests**: 19 pytest cases (fake models, no external services needed)

## 🚀 Quick Start

```bash
# 1. Dependencies
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..

# 2. Local models
ollama pull bge-m3
ollama pull qwen3:4b

# 3. Run → http://127.0.0.1:8000
python backend/main.py
```

Default login `admin / admin123` — change it immediately. Cloud models: Log in → LLM Center → Add provider → pick vendor + paste API key.

### Optional built-in cloud model

The system works fully offline with Ollama. To pre-configure a cloud provider, set an env var (or write to `backend/data/minimax_key.txt`) and restart:

```bash
export CHATKB_MINIMAX_KEY=sk-xxx
```

## 🤖 Agent Workflow

```
Start ─▶ Knowledge Retrieve ─▶ Tool Research (ReAct) ─▶ LLM Draft ─▶ Review Gate ─▶ Answer
                                                     ▲ FAIL: rewrite with reason │
                                                     └───────────────────────────┘
```

- Add/remove nodes, wire edges, edit prompt templates per LLM node (`{{message}}`, `{{knowledge}}`, …) — saving applies to the very next run
- Skills = keyword match + scenario discipline; drop a JSON into `backend/app/agent/skills/`
- Plugins = JSON-defined HTTP endpoints; MCP servers via config

## 📖 Sample Corpus

`knowledge/` ships 11 original "art of speaking" handbooks (workplace, social, praise & criticism, refusal, apology, money talks, icebreakers, group chats, intimate relationships, flirting-tension for her/him). Replace with your own legally-owned books anytime.

## ⚠️ Notes

- Do not upload pirated e-books; only import content you have the rights to use
- API keys are encrypted and stored locally under `backend/data/` (gitignored)
- Change the default password immediately; put a reverse proxy + HTTPS in front before exposing ports

## 📄 License

For study and research. The corpus under `knowledge/` is original to this project and free to use.
