from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from slide2study.models import Chunk, Page


@dataclass(slots=True)
class HierarchicalChunker:
    """Page-grounded chunks with section metadata and controllable overlap."""

    max_chars: int = 500
    overlap_sentences: int = 1

    def chunk(self, pages: list[Page]) -> list[Chunk]:
        chunks: list[Chunk] = []
        current_section: str | None = None
        for page in pages:
            section = _detect_heading(page) or current_section
            current_section = section
            sentences = _split_sentences(page.text)
            if not sentences:
                continue
            windows = _make_windows(sentences, self.max_chars, self.overlap_sentences)
            parent_id = f"{page.document_id}:page:{page.page_number}"
            for offset, text in enumerate(windows):
                identity = f"{page.document_id}:{page.page_number}:{offset}:{text}"
                digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]
                chunks.append(
                    Chunk(
                        chunk_id=f"chk_{digest}",
                        document_id=page.document_id,
                        page_start=page.page_number,
                        page_end=page.page_number,
                        text=text,
                        section=section,
                        parent_id=parent_id,
                        metadata={"source_title": page.title, "window": offset},
                    )
                )
        return chunks


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
