from __future__ import annotations

import math
from dataclasses import dataclass

from slide2study.retrieval import Retriever


@dataclass(slots=True)
class EvaluationSummary:
    queries: int
    recall_at_k: float
    mrr: float
    ndcg_at_k: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "queries": self.queries,
            "recall_at_k": round(self.recall_at_k, 6),
            "mrr": round(self.mrr, 6),
            "ndcg_at_k": round(self.ndcg_at_k, 6),
        }


def evaluate(retriever: Retriever, examples: list[dict], top_k: int = 5) -> EvaluationSummary:
    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    ndcgs: list[float] = []
    for example in examples:
        relevant = set(example.get("relevant_chunk_ids", []))
        relevant_pages = {int(page) for page in example.get("relevant_pages", [])}
        results = retriever.search(example["query"], top_k)
        relevance = [
            int(
                result.chunk.chunk_id in relevant
                or any(
                    result.chunk.page_start <= page <= result.chunk.page_end
                    for page in relevant_pages
                )
            )
            for result in results
        ]
        recalls.append(float(any(relevance)))
        first = next((rank for rank, hit in enumerate(relevance, 1) if hit), None)
        reciprocal_ranks.append(1.0 / first if first else 0.0)
        dcg = sum(hit / math.log2(rank + 1) for rank, hit in enumerate(relevance, 1))
        # Chunk IDs and pages are alternative annotation styles, not additive labels.
        ideal_hits = min(top_k, max(1, len(relevant), len(relevant_pages)))
        idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
        ndcgs.append(dcg / idcg if idcg else 0.0)
    count = len(examples)
    if not count:
        return EvaluationSummary(0, 0.0, 0.0, 0.0)
    return EvaluationSummary(
        count,
        sum(recalls) / count,
        sum(reciprocal_ranks) / count,
        sum(ndcgs) / count,
    )
