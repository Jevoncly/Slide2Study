from __future__ import annotations

from dataclasses import asdict, dataclass

from slide2study.models import Chunk
from slide2study.retrieval import Retriever


@dataclass(slots=True)
class TrainingTriplet:
    """One contrastive/reranker example produced from retrieval errors."""

    query: str
    positive_chunk_id: str
    negative_chunk_id: str
    negative_rank: int
    miner: str
    difficulty: str = "unlabeled"

    def to_dict(self) -> dict:
        return asdict(self)


def mine_hard_negatives(
    retriever: Retriever,
    examples: list[dict],
    chunks: list[Chunk],
    top_k: int = 20,
    miner_name: str = "bm25",
    max_per_query: dict[str, int] | None = None,
) -> list[TrainingTriplet]:
    """Mine high-ranking non-relevant chunks for bi-encoder or cross-encoder training."""
    limits = max_per_query or {}
    unknown = set(limits) - {"hard", "medium", "easy"}
    if unknown or any(limit < 0 for limit in limits.values()):
        raise ValueError("Difficulty limits must be non-negative hard/medium/easy counts")
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    triplets: list[TrainingTriplet] = []
    for example in examples:
        labeled_ids = set(example.get("relevant_chunk_ids", []))
        positive_ids = {chunk_id for chunk_id in labeled_ids if chunk_id in by_id}
        positive_pages = {int(page) for page in example.get("relevant_pages", [])}
        document_id = example.get("document_id")
        positive_ids.update(
            chunk.chunk_id
            for chunk in chunks
            if (document_id is None or chunk.document_id == document_id)
            and any(chunk.page_start <= page <= chunk.page_end for page in positive_pages)
        )
        ranked_results = retriever.search(example["query"], max(top_k, len(chunks)))
        positive_id = next(
            (
                result.chunk.chunk_id
                for result in ranked_results
                if result.chunk.chunk_id in positive_ids
            ),
            None,
        )
        if positive_id is None:
            positive_id = next((value for value in sorted(positive_ids) if value in by_id), None)
        if positive_id is None:
            continue
        selected_by_difficulty = {"hard": 0, "medium": 0, "easy": 0}
        for result in ranked_results:
            if result.rank > top_k:
                break
            if result.chunk.chunk_id in positive_ids:
                continue
            difficulty = _negative_difficulty(result.rank)
            limit = limits.get(difficulty)
            if limit is not None and selected_by_difficulty[difficulty] >= limit:
                continue
            triplets.append(
                TrainingTriplet(
                    query=example["query"],
                    positive_chunk_id=positive_id,
                    negative_chunk_id=result.chunk.chunk_id,
                    negative_rank=result.rank,
                    miner=miner_name,
                    difficulty=difficulty,
                )
            )
            selected_by_difficulty[difficulty] += 1
    return triplets


def _negative_difficulty(rank: int) -> str:
    if rank <= 5:
        return "hard"
    if rank <= 10:
        return "medium"
    return "easy"
