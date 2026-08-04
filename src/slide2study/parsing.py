from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path

from slide2study.models import Page


class DocumentParser(ABC):
    @abstractmethod
    def parse(self, path: str | Path) -> list[Page]:
        """Parse a document into page-level evidence units."""


class TextParser(DocumentParser):
    """Offline-friendly parser; form-feed or `--- page ---` starts a new page."""

    def parse(self, path: str | Path) -> list[Page]:
        source = Path(path)
        raw = source.read_text(encoding="utf-8")
        parts = re.split(r"\f|^\s*---\s*page\s*---\s*$", raw, flags=re.I | re.M)
        return [
            Page(source.stem, number, text.strip(), _explicit_text_heading(text))
            for number, text in enumerate(parts, 1)
            if text.strip()
        ]


class PDFParser(DocumentParser):
    def parse(self, path: str | Path) -> list[Page]:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("PDF support requires: pip install 'slide2study[documents]'") from exc
        source = Path(path)
        reader = PdfReader(str(source))
        pages = []
        for number, pdf_page in enumerate(reader.pages, 1):
            text = (pdf_page.extract_text() or "").strip()
            pages.append(Page(source.stem, number, text))
        return pages


class PPTXParser(DocumentParser):
    def parse(self, path: str | Path) -> list[Page]:
        try:
            from pptx import Presentation
        except ImportError as exc:
            raise RuntimeError("PPTX support requires: pip install 'slide2study[documents]'") from exc
        source = Path(path)
        deck = Presentation(str(source))
        pages = []
        for number, slide in enumerate(deck.slides, 1):
            blocks = []
            title = None
            for shape in slide.shapes:
                if not hasattr(shape, "text") or not shape.text.strip():
                    continue
                value = shape.text.strip()
                blocks.append(value)
                if title is None and getattr(shape, "is_placeholder", False):
                    title = value.splitlines()[0]
            pages.append(Page(source.stem, number, "\n".join(blocks), title))
        return pages


def get_parser(path: str | Path) -> DocumentParser:
    suffix = Path(path).suffix.lower()
    parsers = {".pdf": PDFParser, ".pptx": PPTXParser, ".txt": TextParser, ".md": TextParser}
    try:
        return parsers[suffix]()
    except KeyError as exc:
        raise ValueError(f"Unsupported document type: {suffix or '<none>'}") from exc


def _first_nonempty_line(text: str) -> str | None:
    return next((line.strip() for line in text.splitlines() if line.strip()), None)


def _explicit_text_heading(text: str) -> str | None:
    first = _first_nonempty_line(text)
    return first if first and first.startswith("#") else None
