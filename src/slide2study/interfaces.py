from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol

from slide2study.models import PageSearchResult, SearchResult


@dataclass(slots=True)
class CitedStudyMaterial:
    content: str
    cited_pages: list[int]
    kind: str


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


class Reranker(ABC):
    """Interface for a cross-encoder trained with mined hard negatives."""

    @abstractmethod
    def rerank(self, query: str, candidates: list[SearchResult]) -> list[SearchResult]:
        pass
