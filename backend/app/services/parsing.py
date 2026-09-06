# -*- coding: utf-8 -*-
"""文档解析与分块：pdf/epub/docx/txt/md/html -> (文本, 页码, 章节) -> 分块"""
import re
from pathlib import Path

SENT_SPLIT = re.compile(r"(?<=[。！？!?；;”\n])")


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """返回 (frontmatter字典, 去掉frontmatter的正文)"""
    meta = {}
    body = text
    if text.lstrip().startswith("---"):
        m = re.match(r"\s*---\s*\n(.*?)\n---\s*\n?", text, re.S)
        if m:
            for line in m.group(1).splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip("\"'")
            body = text[m.end():]
    return meta, body


# ---------- 各格式抽取：返回 [(文本, 页码或None, 章节名或None), ...] ----------

def _pdf(path: Path):
    import fitz
    sections = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if text:
                sections.append((text, i, None))
    return sections


def _epub(path: Path):
    import ebooklib
    from bs4 import BeautifulSoup
    from ebooklib import epub
    book = epub.read_epub(str(path))
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
        if text.strip():
            sections.append((text, None, toc_map.get(item.get_name()) or item.get_name()))
    return sections


def _docx(path: Path):
    from docx import Document
    text = "\n".join(p.text for p in Document(str(path)).paragraphs)
    return [(text, None, None)] if text.strip() else []


def _plaintext(path: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [(text, None, None)] if text.strip() else []


def _html(path: Path):
    from bs4 import BeautifulSoup
    text = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser").get_text("\n")
    return [(text, None, None)] if text.strip() else []


EXTRACTORS = {
    ".pdf": _pdf, ".epub": _epub, ".docx": _docx,
    ".html": _html, ".htm": _html, ".txt": _plaintext, ".md": _plaintext,
}

SUPPORTED_EXTS = set(EXTRACTORS)


def extract(path: Path) -> list[tuple[str, int | None, str | None]]:
    sections = EXTRACTORS[path.suffix.lower()](Path(path))
    if path.suffix.lower() == ".pdf" and sum(len(t) for t, _, _ in sections) < 50:
        raise ValueError("几乎提取不到文字，可能是扫描版 PDF，需要先 OCR")
    return sections


def split_sentences(text: str) -> list[str]:
    return [s for s in SENT_SPLIT.split(text.replace("\r\n", "\n")) if s.strip()]


def make_chunks(
    sections: list[tuple[str, int | None, str | None]],
    chunk_size: int = 600,
    chunk_overlap: int = 100,
) -> list[dict]:
    """句子聚合分块，块间保留重叠；返回 [{text, chapter, page}]"""
    chunks = []
    for text, page, chapter in sections:
        sents = split_sentences(text)
        buf: list[str] = []
        buf_len = 0

        def emit():
            body = "".join(buf).strip()
            if body:
                chunks.append({"text": body, "chapter": chapter or "", "page": int(page or 0)})

        for s in sents:
            if buf_len + len(s) > chunk_size and buf:
                emit()
                tail, tlen = [], 0
                for t in reversed(buf):
                    if tlen + len(t) > chunk_overlap:
                        break
                    tail.insert(0, t)
                    tlen += len(t)
                buf, buf_len = list(tail), tlen
            buf.append(s)
            buf_len += len(s)
        emit()
    return chunks
