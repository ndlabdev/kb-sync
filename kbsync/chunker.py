"""Heading-aware chunking.

Each chunk becomes one file in the vector store and is kept below the 800-token static
chunk size we give OpenAI, so OpenAI never splits it again: 1 uploaded file == 1 chunk.
That makes the "chunks embedded" count exact, and lets every chunk carry its own
title, section path and "Article URL:" line, so any retrieved chunk can be cited.

Before chunking, text that helps a human reader but only adds noise to embeddings is
dropped (see prepare_for_embedding). The exported .md files keep everything.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache

from .cleaner import MarkdownDoc

_HEADING = re.compile(r"^(#{2,6})\s+(.*\S)\s*$")
_TOC_ITEM = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+\[[^\]]+\]\(#[^)]*\)\s*$")
_BOILERPLATE = (
    re.compile(r"\badditional questions\b.*\b(support|reach out|contact)", re.I),
    re.compile(r"optisigns is the leader in \[?digital signage software", re.I),
    re.compile(r"^#{1,6}\s*that[’']s all!?\s*$", re.I),
    re.compile(r"^#{1,6}\s*\**that[’']s it!?\**\s*$", re.I),
)
# "### In this article, we'll show how to ..." is an intro sentence styled as a heading.
_LEDE_HEADING = re.compile(r"^#{1,6}\s+(in this article\b.*)$", re.I)
_MAX_HEADING_WORDS = 14


def prepare_for_embedding(body: str) -> str:
    """Drop what helps a reader on the web page but only dilutes search:
    - in-page tables of contents (bullet lists of #anchor links): in long articles they
      fill the first chunk and push the key content into a later, weaker chunk;
    - the support/marketing sign-off repeated at the end of most articles;
    - intro sentences styled as headings, which would otherwise become section names."""
    out: list[str] = []
    in_fence = False
    for line in body.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        if _TOC_ITEM.match(line) or any(pattern.search(line) for pattern in _BOILERPLATE):
            continue
        lede = _LEDE_HEADING.match(line)
        heading = _HEADING.match(line)
        if lede:
            line = lede.group(1)
        elif heading and len(heading.group(2).split()) > _MAX_HEADING_WORDS:
            line = heading.group(2)
        if not line.strip() and out and not out[-1].strip():
            continue
        out.append(line)
    return "\n".join(out).strip()


@dataclass(frozen=True)
class Chunk:
    article_id: int
    index: int
    total: int
    filename: str
    text: str
    tokens: int


@dataclass(frozen=True)
class _Unit:
    path: str
    text: str


# ---------------------------------------------------------------- token counting


@lru_cache(maxsize=1)
def _encoder():
    try:
        import tiktoken

        return tiktoken.get_encoding("o200k_base")
    except Exception:  # offline without a cached encoding: fall back to an estimate
        return None


def count_tokens(text: str) -> int:
    enc = _encoder()
    if enc is not None:
        return len(enc.encode(text))
    return math.ceil(len(text) / 3)  # over-estimates English, so limits stay safe


def _hard_split(text: str, budget: int) -> list[str]:
    enc = _encoder()
    if enc is not None:
        ids = enc.encode(text)
        return [enc.decode(ids[i : i + budget]) for i in range(0, len(ids), budget)]
    step = budget * 3
    return [text[i : i + step] for i in range(0, len(text), step)]


# ---------------------------------------------------------------- markdown structure


def _sections(body: str) -> list[_Unit]:
    """Split on H2-H6 headings (outside code fences). Each section keeps its heading line."""
    sections: list[_Unit] = []
    stack: list[tuple[int, str]] = []
    current_path, current_lines = "", []
    in_fence = False

    def flush() -> None:
        text = "\n".join(current_lines).strip()
        if text:
            sections.append(_Unit(current_path, text))

    for line in body.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        match = None if in_fence else _HEADING.match(line)
        if match:
            flush()
            level, title = len(match[1]), match[2]
            stack = [(lvl, t) for lvl, t in stack if lvl < level] + [(level, title)]
            current_path = " › ".join(t for _, t in stack)
            current_lines = [line]
        else:
            current_lines.append(line)
    flush()
    return sections


def _blocks(text: str) -> list[str]:
    """Paragraph-level blocks; a fenced code block stays one block even with blank lines."""
    blocks, current, in_fence = [], [], False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not line.strip() and not in_fence:
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current))
    # A heading never ends up alone at the bottom of a chunk: glue it to the block after it.
    glued: list[str] = []
    for block in blocks:
        if glued and _HEADING.match(glued[-1]) and "\n" not in glued[-1]:
            glued[-1] = f"{glued[-1]}\n\n{block}"
        else:
            glued.append(block)
    return glued


# ---------------------------------------------------------------- packing


def _header(doc: MarkdownDoc, path: str) -> str:
    title = f"{doc.title} › {path}" if path else doc.title
    return f"# {title}\nArticle URL: {doc.url}\n\n"


def _render(doc: MarkdownDoc, path: str, parts: list[str]) -> str:
    return (_header(doc, path) + "\n\n".join(parts)).strip() + "\n"


# Token counts are not exactly additive across a join, so leave a small margin per unit.
_MARGIN = 8


def chunk_document(doc: MarkdownDoc, max_tokens: int = 700) -> list[Chunk]:
    # 1. Units small enough to stand alone under their own header.
    units: list[_Unit] = []
    for section in _sections(prepare_for_embedding(doc.body)) or [_Unit("", "")]:
        budget = max_tokens - count_tokens(_header(doc, section.path)) - _MARGIN
        if count_tokens(section.text) <= budget:
            units.append(section)
            continue
        for block in _blocks(section.text):
            if count_tokens(block) <= budget:
                units.append(_Unit(section.path, block))
            else:
                units.extend(_Unit(section.path, piece) for piece in _hard_split(block, budget))

    # 2. Greedy packing of consecutive units; a chunk's header names its first unit's section.
    packed: list[tuple[str, list[str]]] = []
    for unit in units:
        if packed:
            path, parts = packed[-1]
            if count_tokens(_render(doc, path, parts + [unit.text])) <= max_tokens:
                parts.append(unit.text)
                continue
        packed.append((unit.path, [unit.text]))

    total = len(packed)
    chunks = []
    for i, (path, parts) in enumerate(packed):
        text = _render(doc, path, parts)
        chunks.append(
            Chunk(
                article_id=doc.article_id,
                index=i,
                total=total,
                filename=f"{doc.slug}--{i:02d}.md",
                text=text,
                tokens=count_tokens(text),
            )
        )
    return chunks
