from __future__ import annotations

import math
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from slide2study.retrieval import Retriever


QUESTION_TYPES = frozenset({"text", "formula", "table_chart", "visual_only", "cross_page"})


@dataclass(slots=True)
class DatasetValidationSummary:
    examples: int
    question_types: dict[str, int]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": True,
            "examples": self.examples,
            "question_types": self.question_types,
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
    examples: list[dict], *, require_question_types: bool = False
) -> DatasetValidationSummary:
    """Validate the JSONL evaluation schema before an experiment is run."""
    errors: list[str] = []
    warnings: list[str] = []
    identifiers: set[str] = set()
    type_counts: Counter[str] = Counter()

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
        if not isinstance(relevant_pages, list) or any(
            isinstance(page, bool) or not isinstance(page, int) or page < 1
            for page in relevant_pages
        ):
            errors.append(f"{prefix}: relevant_pages must be a list of positive integers")
        if not isinstance(relevant_chunks, list) or any(
            not isinstance(chunk_id, str) or not chunk_id.strip()
            for chunk_id in relevant_chunks
        ):
            errors.append(f"{prefix}: relevant_chunk_ids must be a list of non-empty strings")
        if not relevant_pages and not relevant_chunks:
            errors.append(f"{prefix}: provide relevant_pages or relevant_chunk_ids")

        document_id = example.get("document_id")
        if document_id is not None and (
            not isinstance(document_id, str) or not document_id.strip()
        ):
            errors.append(f"{prefix}: document_id must be a non-empty string when provided")

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

    if errors:
        raise ValueError("Invalid evaluation dataset:\n- " + "\n- ".join(errors))
    return DatasetValidationSummary(len(examples), dict(sorted(type_counts.items())), warnings)


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
