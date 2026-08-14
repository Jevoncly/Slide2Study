from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from slide2study.models import Chunk, Page

CHUNK_LEVELS = frozenset({"section", "page", "passage"})


@dataclass(slots=True)
class HierarchicalChunker:
    """Build section, page and passage chunks with traceable parent-child links."""

    max_chars: int = 500
    overlap_sentences: int = 1
    max_section_chars: int = 2000

    def chunk(self, pages: list[Page]) -> list[Chunk]:
        if not pages:
            return []
        pages = sorted(pages, key=lambda page: page.page_number)
        chunks: list[Chunk] = []
        for section_title, section_pages in _group_sections(pages):
            section_id = _stable_id(
                "sec",
                section_pages[0].document_id,
                str(section_pages[0].page_number),
                section_title,
            )
            page_ids = [
                _stable_id("page", page.document_id, str(page.page_number))
                for page in section_pages
            ]
            section_text = "\n\n".join(page.text for page in section_pages if page.text.strip())
            chunks.append(
                Chunk(
                    chunk_id=section_id,
                    document_id=section_pages[0].document_id,
                    page_start=section_pages[0].page_number,
                    page_end=section_pages[-1].page_number,
                    text=_truncate(section_text, self.max_section_chars),
                    section=section_title,
                    level="section",
                    child_ids=page_ids,
                    metadata={
                        "page_count": len(section_pages),
                        "truncated": len(section_text) > self.max_section_chars,
                    },
                )
            )
            for page, page_id in zip(section_pages, page_ids):
                passages = self._passage_chunks(page, section_title, page_id)
                chunks.append(
                    Chunk(
                        chunk_id=page_id,
                        document_id=page.document_id,
                        page_start=page.page_number,
                        page_end=page.page_number,
                        text=page.text,
                        section=section_title,
                        parent_id=section_id,
                        level="page",
                        child_ids=[passage.chunk_id for passage in passages],
                        metadata={"source_title": page.title, **page.metadata},
                    )
                )
                chunks.extend(passages)
        hierarchy_errors = validate_chunk_hierarchy(chunks)
        if hierarchy_errors:
            raise ValueError("Invalid chunk hierarchy: " + "; ".join(hierarchy_errors))
        return chunks

    def _passage_chunks(self, page: Page, section: str, page_id: str) -> list[Chunk]:
        sentences = _split_sentences(page.text)
        windows = _make_windows(sentences, self.max_chars, self.overlap_sentences)
        passages = []
        for offset, text in enumerate(windows):
            passages.append(
                Chunk(
                    chunk_id=_stable_id(
                        "chk", page.document_id, str(page.page_number), str(offset), text
                    ),
                    document_id=page.document_id,
                    page_start=page.page_number,
                    page_end=page.page_number,
                    text=text,
                    section=section,
                    parent_id=page_id,
                    level="passage",
                    metadata={"source_title": page.title, "window": offset},
                )
            )
        return passages


def _group_sections(pages: list[Page]) -> list[tuple[str, list[Page]]]:
    groups: list[tuple[str, list[Page]]] = []
    current_title = _detect_heading(pages[0]) or pages[0].document_id
    current_pages: list[Page] = []
    for index, page in enumerate(pages):
        heading = _detect_heading(page)
        if index > 0 and _starts_section(page, heading):
            groups.append((current_title, current_pages))
            current_title = heading or f"Section {len(groups) + 1}"
            current_pages = []
        current_pages.append(page)
    groups.append((current_title, current_pages))
    return groups


def _starts_section(page: Page, heading: str | None) -> bool:
    if page.metadata.get("section_break") is True:
        return True
    if not heading:
        return False
    normalized = heading.strip("# ")
    patterns = (
        r"^第[0-9一二三四五六七八九十百]+[章节篇单元]",
        r"^(chapter|unit|module|part)\s+[0-9ivx]+\b",
    )
    return any(re.search(pattern, normalized, flags=re.I) for pattern in patterns)


def _detect_heading(page: Page) -> str | None:
    if page.title and len(page.title) <= 100:
        return page.title.strip("# ")
    first = next((line.strip() for line in page.text.splitlines() if line.strip()), "")
    if first.startswith("#") or (0 < len(first) <= 60 and not re.search(r"[。！？.!?]$", first)):
        return first.strip("# ")
    return None


def _split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"[ \t]+", " ", text.strip())
    pieces = re.split(r"(?<=[。！？.!?；;])\s*|\n+", normalized)
    return [piece.strip() for piece in pieces if piece.strip()]


def _make_windows(sentences: list[str], max_chars: int, overlap: int) -> list[str]:
    windows: list[str] = []
    start = 0
    while start < len(sentences):
        end = start
        size = 0
        while end < len(sentences) and (size + len(sentences[end]) <= max_chars or end == start):
            size += len(sentences[end])
            end += 1
        windows.append(" ".join(sentences[start:end]))
        if end >= len(sentences):
            break
        start = max(start + 1, end - max(0, overlap))
    return windows


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1(":".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    candidate = text[:max_chars]
    boundary = max(candidate.rfind(mark) for mark in ("。", "！", "？", ".", "!", "?", "\n"))
    return candidate[: boundary + 1].strip() if boundary >= max_chars // 2 else candidate.strip()


def validate_chunk_hierarchy(chunks: list[Chunk]) -> list[str]:
    """Return structural errors without coupling callers to exceptions."""
    errors: list[str] = []
    by_id: dict[str, Chunk] = {}
    for chunk in chunks:
        if chunk.chunk_id in by_id:
            errors.append(f"duplicate chunk_id {chunk.chunk_id}")
        by_id[chunk.chunk_id] = chunk
    for chunk in chunks:
        if chunk.parent_id:
            parent = by_id.get(chunk.parent_id)
            if parent is None:
                errors.append(f"{chunk.chunk_id} has missing parent {chunk.parent_id}")
            elif chunk.chunk_id not in parent.child_ids:
                errors.append(f"{chunk.chunk_id} is not linked by parent {parent.chunk_id}")
            elif not (
                parent.document_id == chunk.document_id
                and parent.page_start <= chunk.page_start
                and parent.page_end >= chunk.page_end
            ):
                errors.append(f"{chunk.chunk_id} falls outside parent evidence range")
        for child_id in chunk.child_ids:
            child = by_id.get(child_id)
            if child is None:
                errors.append(f"{chunk.chunk_id} has missing child {child_id}")
            elif child.parent_id != chunk.chunk_id:
                errors.append(f"{child_id} does not link back to {chunk.chunk_id}")
    return errors
