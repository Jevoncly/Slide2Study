from __future__ import annotations

import math
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from slide2study.interfaces import PageRetriever
from slide2study.models import Chunk
from slide2study.retrieval import Retriever

QUESTION_TYPES = frozenset({"text", "formula", "table_chart", "visual_only", "cross_page"})
DATASET_SPLITS = frozenset({"train", "dev", "test"})
ANNOTATION_STATUSES = frozenset({"candidate", "verified"})


@dataclass(slots=True)
class DatasetValidationSummary:
    examples: int
    question_types: dict[str, int]
    splits: dict[str, int] = field(default_factory=dict)
    documents: dict[str, int] = field(default_factory=dict)
    annotation_statuses: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": True,
            "examples": self.examples,
            "question_types": self.question_types,
            "splits": self.splits,
            "documents": self.documents,
            "annotation_statuses": self.annotation_statuses,
            "warnings": self.warnings,
        }


@dataclass(slots=True)
class EvaluationSummary:
    queries: int
    recall_at_k: float
    mrr: float
    ndcg_at_k: float
    precision_at_k: float = 0.0
    no_result_rate: float = 0.0
    average_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    by_question_type: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "queries": self.queries,
            "recall_at_k": round(self.recall_at_k, 6),
            "precision_at_k": round(self.precision_at_k, 6),
            "mrr": round(self.mrr, 6),
            "ndcg_at_k": round(self.ndcg_at_k, 6),
            "no_result_rate": round(self.no_result_rate, 6),
            "average_latency_ms": round(self.average_latency_ms, 3),
            "p95_latency_ms": round(self.p95_latency_ms, 3),
            "by_question_type": self.by_question_type,
        }


@dataclass(slots=True)
class _QueryMetrics:
    question_type: str
    recall: float
    precision: float
    reciprocal_rank: float
    ndcg: float
    no_result: float
    latency_ms: float


def validate_dataset(
    examples: list[dict],
    *,
    require_question_types: bool = False,
    require_splits: bool = False,
    require_document_ids: bool = False,
    require_annotation_statuses: bool = False,
    chunks: list[Chunk] | None = None,
) -> DatasetValidationSummary:
    """Validate the JSONL evaluation schema before an experiment is run."""
    errors: list[str] = []
    warnings: list[str] = []
    identifiers: set[str] = set()
    queries: set[tuple[str | None, str]] = set()
    type_counts: Counter[str] = Counter()
    split_counts: Counter[str] = Counter()
    document_counts: Counter[str] = Counter()
    annotation_status_counts: Counter[str] = Counter()
    chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks or []}
    corpus_pages: dict[str, set[int]] = defaultdict(set)
    for chunk in chunks or []:
        corpus_pages[chunk.document_id].update(range(chunk.page_start, chunk.page_end + 1))

    if not examples:
        errors.append("dataset must contain at least one example")

    for line_number, example in enumerate(examples, 1):
        prefix = f"line {line_number}"
        if not isinstance(example, dict):
            errors.append(f"{prefix}: expected a JSON object")
            continue

        identifier = example.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            errors.append(f"{prefix}: id must be a non-empty string")
        elif identifier in identifiers:
            errors.append(f"{prefix}: duplicate id {identifier!r}")
        else:
            identifiers.add(identifier)

        query = example.get("query")
        if not isinstance(query, str) or not query.strip():
            errors.append(f"{prefix}: query must be a non-empty string")

        relevant_pages = example.get("relevant_pages", [])
        relevant_chunks = example.get("relevant_chunk_ids", [])
        pages_are_valid = isinstance(relevant_pages, list) and not any(
            isinstance(page, bool) or not isinstance(page, int) or page < 1
            for page in relevant_pages
        )
        chunks_are_valid = isinstance(relevant_chunks, list) and not any(
            not isinstance(chunk_id, str) or not chunk_id.strip()
            for chunk_id in relevant_chunks
        )
        if not pages_are_valid:
            errors.append(f"{prefix}: relevant_pages must be a list of positive integers")
        if not chunks_are_valid:
            errors.append(f"{prefix}: relevant_chunk_ids must be a list of non-empty strings")
        if not relevant_pages and not relevant_chunks:
            errors.append(f"{prefix}: provide relevant_pages or relevant_chunk_ids")

        document_id = example.get("document_id")
        if document_id is None:
            document_counts["unlabeled"] += 1
            if require_document_ids:
                errors.append(f"{prefix}: document_id is missing")
        elif not isinstance(document_id, str) or not document_id.strip():
            errors.append(f"{prefix}: document_id must be a non-empty string when provided")
        else:
            document_counts[document_id] += 1
            if chunks is not None and document_id not in corpus_pages:
                errors.append(f"{prefix}: document_id {document_id!r} is not in the corpus")

        if isinstance(query, str) and query.strip():
            query_key = (
                document_id if isinstance(document_id, str) else None,
                query.strip().casefold(),
            )
            if query_key in queries:
                errors.append(f"{prefix}: duplicate query within the same document")
            queries.add(query_key)

        if chunks is not None:
            if pages_are_valid and relevant_pages and not isinstance(document_id, str):
                errors.append(f"{prefix}: document_id is required to validate relevant_pages")
            elif (
                pages_are_valid
                and isinstance(document_id, str)
                and document_id in corpus_pages
            ):
                missing_pages = sorted(set(relevant_pages) - corpus_pages[document_id])
                if missing_pages:
                    errors.append(f"{prefix}: relevant page(s) not in the corpus: {missing_pages}")
            if chunks_are_valid:
                missing_chunks = sorted(set(relevant_chunks) - chunk_by_id.keys())
                if missing_chunks:
                    errors.append(
                        f"{prefix}: relevant chunk(s) not in the corpus: {missing_chunks}"
                    )
                elif isinstance(document_id, str):
                    foreign = sorted(
                        chunk_id
                        for chunk_id in relevant_chunks
                        if chunk_by_id[chunk_id].document_id != document_id
                    )
                    if foreign:
                        errors.append(
                            f"{prefix}: relevant chunk(s) belong to another document: {foreign}"
                        )

        question_type = example.get("question_type")
        if question_type is None:
            type_counts["unlabeled"] += 1
            message = f"{prefix}: question_type is missing"
            if require_question_types:
                errors.append(message)
            else:
                warnings.append(message)
        elif not isinstance(question_type, str) or question_type not in QUESTION_TYPES:
            expected = ", ".join(sorted(QUESTION_TYPES))
            errors.append(f"{prefix}: question_type must be one of: {expected}")
        else:
            type_counts[question_type] += 1

        split = example.get("split")
        if split is None:
            split_counts["unlabeled"] += 1
            message = f"{prefix}: split is missing"
            if require_splits:
                errors.append(message)
            else:
                warnings.append(message)
        elif not isinstance(split, str) or split not in DATASET_SPLITS:
            expected = ", ".join(sorted(DATASET_SPLITS))
            errors.append(f"{prefix}: split must be one of: {expected}")
        else:
            split_counts[split] += 1

        annotation_status = example.get("annotation_status")
        if annotation_status is None:
            annotation_status_counts["unlabeled"] += 1
            message = f"{prefix}: annotation_status is missing"
            if require_annotation_statuses:
                errors.append(message)
            else:
                warnings.append(message)
        elif (
            not isinstance(annotation_status, str)
            or annotation_status not in ANNOTATION_STATUSES
        ):
            expected = ", ".join(sorted(ANNOTATION_STATUSES))
            errors.append(f"{prefix}: annotation_status must be one of: {expected}")
        else:
            annotation_status_counts[annotation_status] += 1

    if errors:
        raise ValueError("Invalid evaluation dataset:\n- " + "\n- ".join(errors))
    return DatasetValidationSummary(
        examples=len(examples),
        question_types=dict(sorted(type_counts.items())),
        splits=dict(sorted(split_counts.items())),
        documents=dict(sorted(document_counts.items())),
        annotation_statuses=dict(sorted(annotation_status_counts.items())),
        warnings=warnings,
    )


def _summarize(rows: list[_QueryMetrics], *, include_types: bool) -> EvaluationSummary:
    count = len(rows)
    if not count:
        return EvaluationSummary(0, 0.0, 0.0, 0.0)
    latencies = sorted(row.latency_ms for row in rows)
    p95_index = max(0, math.ceil(0.95 * count) - 1)
    summary = EvaluationSummary(
        queries=count,
        recall_at_k=sum(row.recall for row in rows) / count,
        precision_at_k=sum(row.precision for row in rows) / count,
        mrr=sum(row.reciprocal_rank for row in rows) / count,
        ndcg_at_k=sum(row.ndcg for row in rows) / count,
        no_result_rate=sum(row.no_result for row in rows) / count,
        average_latency_ms=sum(latencies) / count,
        p95_latency_ms=latencies[p95_index],
    )
    if include_types:
        grouped: dict[str, list[_QueryMetrics]] = defaultdict(list)
        for row in rows:
            grouped[row.question_type].append(row)
        summary.by_question_type = {
            question_type: _summarize(group, include_types=False).to_dict()
            for question_type, group in sorted(grouped.items())
        }
    return summary


def evaluate(retriever: Retriever, examples: list[dict], top_k: int = 5) -> EvaluationSummary:
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    query_metrics: list[_QueryMetrics] = []
    for example in examples:
        relevant = set(example.get("relevant_chunk_ids", []))
        relevant_pages = {int(page) for page in example.get("relevant_pages", [])}
        expected_document = example.get("document_id")
        started = time.perf_counter_ns()
        results = retriever.search(example["query"], top_k)
        latency_ms = (time.perf_counter_ns() - started) / 1_000_000
        relevance = [
            int(
                result.chunk.chunk_id in relevant
                or (
                    (expected_document is None or result.chunk.document_id == expected_document)
                    and any(
                        result.chunk.page_start <= page <= result.chunk.page_end
                        for page in relevant_pages
                    )
                )
            )
            for result in results
        ]
        first = next((rank for rank, hit in enumerate(relevance, 1) if hit), None)
        dcg = sum(hit / math.log2(rank + 1) for rank, hit in enumerate(relevance, 1))
        # Chunk IDs and pages are alternative annotation styles, not additive labels.
        # A page label can make several hierarchy levels relevant. Include those
        # observed relevant chunks so mixed-level nDCG remains bounded by 1.
        ideal_hits = min(top_k, max(1, len(relevant), len(relevant_pages), sum(relevance)))
        idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
        query_metrics.append(
            _QueryMetrics(
                question_type=example.get("question_type", "unlabeled"),
                recall=float(any(relevance)),
                precision=sum(relevance) / top_k,
                reciprocal_rank=1.0 / first if first else 0.0,
                ndcg=dcg / idcg if idcg else 0.0,
                no_result=float(not results),
                latency_ms=latency_ms,
            )
        )
    return _summarize(query_metrics, include_types=True)


def evaluate_page_retrieval(
    retriever: PageRetriever, examples: list[dict], top_k: int = 5
) -> EvaluationSummary:
    """Evaluate query-to-page retrieval with the same aggregate report schema."""
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    query_metrics: list[_QueryMetrics] = []
    for example in examples:
        relevant_pages = {int(page) for page in example.get("relevant_pages", [])}
        expected_document = example.get("document_id")
        started = time.perf_counter_ns()
        results = retriever.search(example["query"], top_k)
        latency_ms = (time.perf_counter_ns() - started) / 1_000_000
        relevance = [
            int(
                result.page.document_id == expected_document
                and result.page.page_number in relevant_pages
            )
            for result in results
        ]
        first = next((rank for rank, hit in enumerate(relevance, 1) if hit), None)
        dcg = sum(hit / math.log2(rank + 1) for rank, hit in enumerate(relevance, 1))
        ideal_hits = min(top_k, max(1, len(relevant_pages)))
        idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
        query_metrics.append(
            _QueryMetrics(
                question_type=example.get("question_type", "unlabeled"),
                recall=float(any(relevance)),
                precision=sum(relevance) / top_k,
                reciprocal_rank=1.0 / first if first else 0.0,
                ndcg=dcg / idcg if idcg else 0.0,
                no_result=float(not results),
                latency_ms=latency_ms,
            )
        )
    return _summarize(query_metrics, include_types=True)


def compare_page_retrievers(
    retrievers: dict[str, PageRetriever], examples: list[dict], top_k: int = 10
) -> list[dict]:
    """Record per-query rankings for failure analysis across page retrievers."""
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    comparisons = []
    for example in examples:
        document_id = example.get("document_id")
        relevant_pages = {int(page) for page in example.get("relevant_pages", [])}
        systems = {}
        for name, retriever in retrievers.items():
            results = retriever.search(example["query"], top_k)
            first_relevant_rank = next(
                (
                    result.rank
                    for result in results
                    if result.page.document_id == document_id
                    and result.page.page_number in relevant_pages
                ),
                None,
            )
            systems[name] = {
                "hit_at_k": first_relevant_rank is not None,
                "first_relevant_rank": first_relevant_rank,
                "top_pages": [
                    {
                        "document_id": result.page.document_id,
                        "page_number": result.page.page_number,
                        "rank": result.rank,
                        "score": result.score,
                    }
                    for result in results
                ],
            }
        comparisons.append(
            {
                "id": example.get("id"),
                "query": example["query"],
                "question_type": example.get("question_type"),
                "document_id": document_id,
                "relevant_pages": sorted(relevant_pages),
                "systems": systems,
            }
        )
    return comparisons
