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

    def to_dict(self) -> dict:
        return asdict(self)


def mine_hard_negatives(
    retriever: Retriever,
    examples: list[dict],
    chunks: list[Chunk],
    top_k: int = 20,
    miner_name: str = "bm25",
) -> list[TrainingTriplet]:
    """Mine high-ranking non-relevant chunks for bi-encoder or cross-encoder training."""
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    triplets: list[TrainingTriplet] = []
    for example in examples:
        positive_ids = set(example.get("relevant_chunk_ids", []))
        positive_pages = {int(page) for page in example.get("relevant_pages", [])}
        if not positive_ids:
            positive_ids = {
                chunk.chunk_id
                for chunk in chunks
                if any(chunk.page_start <= page <= chunk.page_end for page in positive_pages)
            }
        positive_id = next((value for value in sorted(positive_ids) if value in by_id), None)
        if positive_id is None:
            continue
        for result in retriever.search(example["query"], top_k):
            if result.chunk.chunk_id in positive_ids:
                continue
            triplets.append(
                TrainingTriplet(
                    query=example["query"],
                    positive_chunk_id=positive_id,
                    negative_chunk_id=result.chunk.chunk_id,
                    negative_rank=result.rank,
                    miner=miner_name,
                )
            )
    return triplets
