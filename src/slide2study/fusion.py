from __future__ import annotations

from collections.abc import Mapping, Sequence

from slide2study.interfaces import PageRetriever
from slide2study.models import Chunk, PageSearchResult, RenderedPage
from slide2study.retrieval import BM25Retriever


def _page_key(page: RenderedPage) -> tuple[str, int]:
    return page.document_id, page.page_number


class BM25PageRetriever:
    """Project ranked BM25 chunks onto their rendered evidence pages."""

    def __init__(
        self,
        chunks: Sequence[Chunk],
        pages: Sequence[RenderedPage],
        candidate_k: int = 50,
    ):
        if candidate_k < 1:
            raise ValueError("candidate_k must be at least 1")
        self.retriever = BM25Retriever(list(chunks))
        self.pages_by_key = {_page_key(page): page for page in pages}
        self.candidate_k = candidate_k

    def search(self, query: str, top_k: int = 5) -> list[PageSearchResult]:
        if top_k <= 0:
            return []
        best_by_page: dict[tuple[str, int], tuple[int, float, RenderedPage]] = {}
        for result in self.retriever.search(query, self.candidate_k):
            for page_number in range(result.chunk.page_start, result.chunk.page_end + 1):
                key = (result.chunk.document_id, page_number)
                page = self.pages_by_key.get(key)
                if page is None or key in best_by_page:
                    continue
                best_by_page[key] = (result.rank, result.score, page)
        ranked = sorted(
            best_by_page.values(),
            key=lambda item: (item[0], -item[1], item[2].document_id, item[2].page_number),
        )
        return [
            PageSearchResult(page, round(score, 8), rank)
            for rank, (_, score, page) in enumerate(ranked[:top_k], 1)
        ]


class ReciprocalRankFusionRetriever:
    """Fuse page rankings without assuming comparable source scores."""

    def __init__(
        self,
        retrievers: Mapping[str, PageRetriever],
        weights: Mapping[str, float] | None = None,
        rrf_k: int = 60,
        candidate_k: int = 50,
    ):
        if not retrievers:
            raise ValueError("At least one page retriever is required")
        if rrf_k < 0:
            raise ValueError("rrf_k cannot be negative")
        if candidate_k < 1:
            raise ValueError("candidate_k must be at least 1")
        self.retrievers = dict(retrievers)
        self.weights = {name: 1.0 for name in retrievers}
        if weights:
            unknown = set(weights) - set(retrievers)
            if unknown:
                raise ValueError(f"Weights reference unknown retrievers: {sorted(unknown)}")
            self.weights.update(weights)
        if any(weight < 0 for weight in self.weights.values()):
            raise ValueError("Retriever weights cannot be negative")
        if not any(self.weights.values()):
            raise ValueError("At least one retriever weight must be positive")
        self.rrf_k = rrf_k
        self.candidate_k = candidate_k

    def search(self, query: str, top_k: int = 5) -> list[PageSearchResult]:
        if top_k <= 0:
            return []
        scores: dict[tuple[str, int], float] = {}
        pages: dict[tuple[str, int], RenderedPage] = {}
        best_rank: dict[tuple[str, int], int] = {}
        for name, retriever in self.retrievers.items():
            weight = self.weights[name]
            if weight == 0:
                continue
            for result in retriever.search(query, self.candidate_k):
                key = _page_key(result.page)
                pages[key] = result.page
                scores[key] = scores.get(key, 0.0) + weight / (self.rrf_k + result.rank)
                best_rank[key] = min(best_rank.get(key, result.rank), result.rank)
        ranked_keys = sorted(
            scores,
            key=lambda key: (-scores[key], best_rank[key], key[0], key[1]),
        )
        return [
            PageSearchResult(pages[key], round(scores[key], 8), rank)
            for rank, key in enumerate(ranked_keys[:top_k], 1)
        ]
