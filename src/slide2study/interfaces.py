from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Protocol

from slide2study.models import PageSearchResult, SearchResult


@dataclass(frozen=True, slots=True)
class EvidenceCitation:
    evidence_id: str
    document_id: str
    page_start: int
    page_end: int
    source_name: str
    chunk_id: str

    @property
    def label(self) -> str:
        page_label = (
            f"p.{self.page_start}"
            if self.page_start == self.page_end
            else f"pp.{self.page_start}-{self.page_end}"
        )
        return f"[{self.source_name}, {page_label}]"

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "label": self.label}


@dataclass(slots=True)
class CitedStudyMaterial:
    content: str
    citations: list[EvidenceCitation]
    kind: str
    refused: bool = False
    refusal_reason: str | None = None

    @property
    def cited_pages(self) -> list[int]:
        return sorted(
            {
                page
                for citation in self.citations
                for page in range(citation.page_start, citation.page_end + 1)
            }
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "content": self.content,
            "kind": self.kind,
            "refused": self.refused,
            "refusal_reason": self.refusal_reason,
            "citations": [citation.to_dict() for citation in self.citations],
            "cited_pages": self.cited_pages,
        }


class StudyMaterialGenerator(ABC):
    """Interface for cited notes, flashcards and multi-level question generation."""

    @abstractmethod
    def generate(self, query: str, evidence: list[SearchResult], kind: str) -> CitedStudyMaterial:
        pass


class MultimodalPageEncoder(ABC):
    """Interface for trainable page-image/text contrastive encoders."""

    @abstractmethod
    def encode_pages(self, image_paths: list[str]) -> list[list[float]]:
        pass

    @abstractmethod
    def encode_queries(self, queries: list[str]) -> list[list[float]]:
        pass


class PageRetriever(Protocol):
    """Common query-to-page interface used by visual and fused retrieval."""

    def search(self, query: str, top_k: int = 5) -> list[PageSearchResult]: ...


class TextEncoder(Protocol):
    """Batch encoder for asymmetric query-to-passage retrieval."""

    def encode_documents(self, texts: list[str]) -> list[list[float]]: ...

    def encode_queries(self, queries: list[str]) -> list[list[float]]: ...


class Reranker(ABC):
    """Interface for a cross-encoder trained with mined hard negatives."""

    @abstractmethod
    def rerank(self, query: str, candidates: list[SearchResult]) -> list[SearchResult]:
        pass
