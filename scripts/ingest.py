# -*- coding: utf-8 -*-
"""
把 knowledge/（书籍等文档）和 personal/（人设/关系/雷区档案）
解析 -> 分块 -> Ollama 向量模型嵌入 -> 存入本地向量库（Chroma）

用法：
    python scripts/ingest.py

支持的格式：pdf / epub / docx / txt / md / html
扫描版 PDF（图片型）提取不出文字，需要先 OCR。
"""
import hashlib
import re
import sys
from pathlib import Path

import chromadb
import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = ROOT / "knowledge"
PERSONAL_DIR = ROOT / "personal"
DB_DIR = ROOT / "db"

OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "bge-m3"
COLLECTION = "chat_kb"  # 新版 Chroma 要求集合名至少 3 个字符
CHUNK_SIZE = 600      # 每块目标长度（字符，中文）
CHUNK_OVERLAP = 100   # 相邻块重叠，避免句子被切断丢失上下文
EMBED_BATCH = 32
SUPPORTED = {".pdf", ".epub", ".docx", ".txt", ".md", ".html", ".htm"}


# ---------- 各格式抽取：返回 [(文本, 页码或None, 章节名或None), ...] ----------

def extract_pdf(path: Path):
    import fitz  # pymupdf
    sections = []
    doc = fitz.open(path)
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        if text:
            sections.append((text, i, None))
    if sum(len(t) for t, _, _ in sections) < 50:
        print(f"  [警告] {path.name} 几乎提取不到文字，可能是扫描版 PDF，需要先 OCR 才能入库")
    return sections


def extract_epub(path: Path):
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup
    book = epub.read_epub(str(path))
    # 建立 href -> 章节标题 的映射，方便块元数据带章节名
    toc_map = {}

    def walk(items):
        for it in items:
            if isinstance(it, tuple):
                walk(it[1])
            elif hasattr(it, "href"):
                toc_map[it.href] = getattr(it, "title", "") or ""

    walk(book.toc)

    sections = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        html = item.get_content().decode("utf-8", errors="ignore")
        text = BeautifulSoup(html, "html.parser").get_text("\n")
        title = toc_map.get(item.get_name()) or item.get_name()
        if text.strip():
            sections.append((text, None, title))
    return sections


def extract_docx(path: Path):
    from docx import Document
    doc = Document(str(path))
    text = "\n".join(p.text for p in doc.paragraphs)
    return [(text, None, None)] if text.strip() else []


def extract_plaintext(path: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [(text, None, None)] if text.strip() else []


def extract_html(path: Path):
    from bs4 import BeautifulSoup
    text = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser").get_text("\n")
    return [(text, None, None)] if text.strip() else []


EXTRACTORS = {
    ".pdf": extract_pdf,
    ".epub": extract_epub,
    ".docx": extract_docx,
    ".html": extract_html,
    ".htm": extract_html,
    ".txt": extract_plaintext,
    ".md": extract_plaintext,
}


# ---------- 分块 ----------

SENT_SPLIT = re.compile(r"(?<=[。！？!?；;”\n])")


def split_sentences(text: str):
    return [s for s in SENT_SPLIT.split(text) if s.strip()]


def make_chunks(sections, source: str):
    """按句子聚合成 ~CHUNK_SIZE 的块，块间保留 CHUNK_OVERLAP 重叠"""
    chunks = []
    for text, page, chapter in sections:
        sents = split_sentences(text.replace("\r\n", "\n"))
        meta = {"source": source, "chapter": chapter or "", "page": int(page or 0)}

        def emit(body):
            if body:
                chunks.append((body, meta))

        buf, buf_len = [], 0
        for s in sents:
            if buf_len + len(s) > CHUNK_SIZE and buf:
                emit("".join(buf).strip())
                tail, tlen = [], 0
                for t in reversed(buf):
                    if tlen + len(t) > CHUNK_OVERLAP:
                        break
                    tail.insert(0, t)
                    tlen += len(t)
                buf, buf_len = list(tail), tlen
            buf.append(s)
            buf_len += len(s)
        emit("".join(buf).strip())
    return chunks


def parse_person(text: str) -> str:
    """personal/ 下的 markdown 用 frontmatter 写 person: 名字，检索时可按人过滤"""
    m = re.search(r"^person:\s*(.+)$", text[:500], re.M)
    return m.group(1).strip().strip("\"'") if m else ""


# ---------- 嵌入 ----------

def ollama_embed(texts):
    out = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i:i + EMBED_BATCH]
        r = requests.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": EMBED_MODEL, "input": batch},
            timeout=300,
        )
        r.raise_for_status()
        out.extend(r.json()["embeddings"])
    return out


def main():
    jobs = []  # (kind, person, file)
    if PERSONAL_DIR.exists():
        jobs += [("personal", f) for f in sorted(PERSONAL_DIR.glob("*")) if f.suffix.lower() in SUPPORTED]
    if KNOWLEDGE_DIR.exists():
        jobs += [("book", f) for f in sorted(KNOWLEDGE_DIR.glob("*")) if f.suffix.lower() in SUPPORTED]

    if not jobs:
        print("knowledge/ 和 personal/ 里没有可入库的文件。")
        print(f"支持的格式：{', '.join(sorted(SUPPORTED))}")
        return

    print(f"共 {len(jobs)} 个文件待入库，嵌入模型：{EMBED_MODEL}\n")

    client = chromadb.PersistentClient(path=str(DB_DIR))
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    col = client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})

    total_chunks = 0
    for kind, path in jobs:
        source = path.name
        try:
            if kind == "personal":
                raw = path.read_text(encoding="utf-8", errors="ignore")
                body = re.sub(r"^---.*?---\s*", "", raw, count=1, flags=re.S)
                sections = [(body, None, None)] if body.strip() else []
            else:
                sections = EXTRACTORS[path.suffix.lower()](path)
        except Exception as e:
            print(f"[跳过] {source}: 解析失败 {e}")
            continue
        if not sections:
            print(f"[跳过] {source}: 没有可提取的文本")
            continue

        chunks = make_chunks(sections, source)
        texts = [c[0] for c in chunks]
        metas = []
        for _, m in chunks:
            m = dict(m)
            m["kind"] = kind
            if kind == "personal":
                m["person"] = parse_person(path.read_text(encoding="utf-8", errors="ignore"))
            metas.append(m)

        embeddings = ollama_embed(texts)
        ids = [hashlib.md5(f"{source}#{i}".encode()).hexdigest() for i in range(len(texts))]

        for i in range(0, len(texts), 64):
            col.add(
                ids=ids[i:i + 64],
                embeddings=embeddings[i:i + 64],
                documents=texts[i:i + 64],
                metadatas=metas[i:i + 64],
            )
        total_chunks += len(texts)
        print(f"[完成] ({kind}) {source}: {len(texts)} 块")

    print(f"\n入库完成，共 {total_chunks} 块，向量库位置：{DB_DIR}")


if __name__ == "__main__":
    main()
