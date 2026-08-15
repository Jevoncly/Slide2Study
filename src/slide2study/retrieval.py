from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from collections.abc import Sequence

from slide2study.interfaces import TextEncoder
from slide2study.models import Chunk, SearchResult


def mixed_tokenize(text: str) -> list[str]:
    """Dependency-free tokenizer: Latin words plus Chinese unigrams and bigrams."""
    lowered = text.lower()
    latin = re.findall(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*", lowered)
    formula = re.findall(r"[\u0370-\u03ff]+|[+*/=^]+", lowered)
    cjk_runs = re.findall(r"[\u3400-\u9fff]+", lowered)
    cjk: list[str] = []
    for run in cjk_runs:
        cjk.extend(run)
        cjk.extend(run[index : index + 2] for index in range(len(run) - 1))
    return latin + formula + cjk


class Retriever(ABC):
    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Return ranked evidence chunks."""


class BM25Retriever(Retriever):
    def __init__(
        self,
        chunks: list[Chunk],
        k1: float = 1.5,
        b: float = 0.75,
        level_weights: dict[str, float] | None = None,
        exclude_low_value: bool = True,
    ):
        self.chunks = [
            chunk
            for chunk in chunks
            if not (exclude_low_value and chunk.metadata.get("text_retrieval_excluded", False))
        ]
        self.k1 = k1
        self.b = b
        self.level_weights = level_weights or {"section": 0.65, "page": 0.85, "passage": 1.0}
        self.term_frequencies = [Counter(mixed_tokenize(chunk.text)) for chunk in self.chunks]
        self.lengths = [sum(counter.values()) for counter in self.term_frequencies]
        self.avg_length = sum(self.lengths) / len(self.lengths) if self.lengths else 0.0
        document_frequency: dict[str, int] = defaultdict(int)
        for terms in self.term_frequencies:
            for term in terms:
                document_frequency[term] += 1
        total = len(chunks)
        self.idf = {
            term: math.log(1 + (total - count + 0.5) / (count + 0.5))
            for term, count in document_frequency.items()
        }

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        query_terms = mixed_tokenize(query)
        scored: list[tuple[float, int]] = []
        for index, frequencies in enumerate(self.term_frequencies):
            score = 0.0
            length_norm = 1 - self.b
            if self.avg_length:
                length_norm += self.b * self.lengths[index] / self.avg_length
            for term in query_terms:
                frequency = frequencies.get(term, 0)
                if frequency:
                    score += self.idf.get(term, 0.0) * (
                        frequency * (self.k1 + 1) / (frequency + self.k1 * length_norm)
                    )
            if score > 0:
                score *= self.level_weights.get(self.chunks[index].level, 1.0)
                scored.append((score, index))
        scored.sort(key=lambda pair: (-pair[0], self.chunks[pair[1]].chunk_id))
        return [
            SearchResult(self.chunks[index], score, rank)
            for rank, (score, index) in enumerate(scored[:top_k], 1)
        ]


class DenseRetriever(Retriever):
    """Cosine-similarity retrieval over cached or freshly encoded chunks."""

    def __init__(
        self,
        chunks: Sequence[Chunk],
        encoder: TextEncoder,
        embeddings: Sequence[Sequence[float]] | None = None,
    ):
        self.chunks = list(chunks)
        self.encoder = encoder
        vectors = embeddings
        if vectors is None:
            vectors = encoder.encode_documents([chunk.text for chunk in self.chunks])
        self.embeddings = _validate_and_normalize(vectors, len(self.chunks))

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        if top_k <= 0:
            return []
        query_vectors = self.encoder.encode_queries([query])
        query_vector = _validate_and_normalize(query_vectors, 1)[0]
        if self.embeddings and len(query_vector) != len(self.embeddings[0]):
            raise ValueError("Query and chunk embeddings must have the same dimensions")
        scored = [
            (sum(left * right for left, right in zip(query_vector, vector)), index)
            for index, vector in enumerate(self.embeddings)
        ]
        scored.sort(key=lambda item: (-item[0], self.chunks[item[1]].chunk_id))
        return [
            SearchResult(self.chunks[index], round(score, 8), rank)
            for rank, (score, index) in enumerate(scored[:top_k], 1)
        ]


def _validate_and_normalize(
    embeddings: Sequence[Sequence[float]], expected_count: int
) -> list[list[float]]:
    vectors = [[float(value) for value in vector] for vector in embeddings]
    if len(vectors) != expected_count:
        raise ValueError(f"Expected {expected_count} embedding(s), received {len(vectors)}")
    dimensions = {len(vector) for vector in vectors}
    if len(dimensions) > 1 or (vectors and not next(iter(dimensions))):
        raise ValueError("Embeddings must have one non-zero shared dimension")
    normalized = []
    for vector in vectors:
        norm = math.sqrt(sum(value * value for value in vector))
        if not math.isfinite(norm) or norm == 0:
            raise ValueError("Embeddings must contain finite non-zero vectors")
        normalized.append([value / norm for value in vector])
    return normalized
