from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

from slide2study.interfaces import StudyMaterialGenerator
from slide2study.models import SearchResult


class ChunkRetriever(Protocol):
    def search(self, query: str, top_k: int = 5) -> list[SearchResult]: ...


@dataclass(slots=True)
class GenerationMetrics:
    queries: int
    answerable_queries: int
    unanswerable_queries: int
    answered_queries: int
    refusal_accuracy: float
    citation_validity: float
    citation_accuracy: float
    citation_coverage: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def evaluate_generation(
    generator: StudyMaterialGenerator,
    retriever: ChunkRetriever,
    examples: list[dict],
    top_k: int = 5,
) -> tuple[GenerationMetrics, list[dict]]:
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    diagnostics = []
    correct_refusals = 0
    valid_citations = 0
    total_citations = 0
    accurate_citations = 0
    covered_answers = 0
    answerable_queries = 0
    answered_queries = 0

    for index, example in enumerate(examples, 1):
        query = str(example.get("query", "")).strip()
        if not query:
            raise ValueError(f"Generation example {index} has no query")
        answerable = bool(example.get("answerable", True))
        answerable_queries += int(answerable)
        evidence = retriever.search(query, top_k)
        material = generator.generate(query, evidence, "answer")
        answered_queries += int(not material.refused)
        correct_refusals += int(material.refused == (not answerable))

        retrieved_by_id = {result.chunk.chunk_id: result.chunk for result in evidence}
        relevant_document = example.get("document_id")
        relevant_pages = {int(page) for page in example.get("relevant_pages", [])}
        correct_for_query = False
        for citation in material.citations:
            total_citations += 1
            chunk = retrieved_by_id.get(citation.chunk_id)
            valid = bool(
                chunk
                and citation.document_id == chunk.document_id
                and citation.page_start == chunk.page_start
                and citation.page_end == chunk.page_end
            )
            valid_citations += int(valid)
            cited_pages = set(range(citation.page_start, citation.page_end + 1))
            accurate = bool(
                answerable
                and citation.document_id == relevant_document
                and cited_pages & relevant_pages
            )
            accurate_citations += int(accurate)
            correct_for_query = correct_for_query or accurate
        covered_answers += int(answerable and correct_for_query)
        diagnostics.append(
            {
                "id": example.get("id", f"example-{index}"),
                "query": query,
                "answerable": answerable,
                "refused": material.refused,
                "refusal_reason": material.refusal_reason,
                "retrieved_chunk_ids": list(retrieved_by_id),
                "cited_chunk_ids": [citation.chunk_id for citation in material.citations],
                "has_accurate_citation": correct_for_query,
            }
        )

    queries = len(examples)
    metrics = GenerationMetrics(
        queries=queries,
        answerable_queries=answerable_queries,
        unanswerable_queries=queries - answerable_queries,
        answered_queries=answered_queries,
        refusal_accuracy=round(correct_refusals / queries, 6) if queries else 0.0,
        citation_validity=round(valid_citations / total_citations, 6) if total_citations else 1.0,
        citation_accuracy=(
            round(accurate_citations / total_citations, 6) if total_citations else 0.0
        ),
        citation_coverage=(
            round(covered_answers / answerable_queries, 6) if answerable_queries else 1.0
        ),
    )
    return metrics, diagnostics
