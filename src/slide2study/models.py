from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Page:
    document_id: str
    page_number: int
    text: str
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ParseReport:
    document_id: str
    page_count: int
    nonempty_pages: int
    total_characters: int
    empty_pages: list[int] = field(default_factory=list)
    low_text_pages: list[int] = field(default_factory=list)
    image_pages: list[int] = field(default_factory=list)
    requires_vision_pages: list[int] = field(default_factory=list)
    low_value_pages: list[int] = field(default_factory=list)
    text_retrieval_excluded_pages: list[int] = field(default_factory=list)
    page_roles: dict[str, int] = field(default_factory=dict)
    removed_boilerplate_lines: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["text_coverage"] = (
            round(self.nonempty_pages / self.page_count, 6) if self.page_count else 0.0
        )
        return value


@dataclass(slots=True)
class Chunk:
    chunk_id: str
    document_id: str
    page_start: int
    page_end: int
    text: str
    section: str | None = None
    parent_id: str | None = None
    level: str = "passage"
    child_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Chunk":
        return cls(**value)


@dataclass(slots=True)
class SearchResult:
    chunk: Chunk
    score: float
    rank: int

    def to_dict(self) -> dict[str, Any]:
        return {"score": self.score, "rank": self.rank, "chunk": self.chunk.to_dict()}


@dataclass(slots=True)
class RenderedPage:
    document_id: str
    page_number: int
    image_path: str
    source_path: str
    width: int
    height: int
    sha256: str
    requires_vision: bool = False
    role: str = "content"
    visual_risk_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RenderedPage":
        return cls(**value)


@dataclass(slots=True)
class PageSearchResult:
    page: RenderedPage
    score: float
    rank: int

    def to_dict(self) -> dict[str, Any]:
        return {"score": self.score, "rank": self.rank, "page": self.page.to_dict()}
