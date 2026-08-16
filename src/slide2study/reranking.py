from __future__ import annotations

import json
import math
import random
from pathlib import Path

from slide2study.interfaces import Reranker
from slide2study.models import Chunk, SearchResult
from slide2study.retrieval import Retriever


def build_reranker_pairs(triplets: list[dict], chunks: list[Chunk]) -> tuple[list[dict], dict]:
    """Expand reviewed triplets into deduplicated positive and negative text pairs."""
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    labels: dict[tuple[str, str], float] = {}
    queries = set()
    for row_number, triplet in enumerate(triplets, 1):
        query = str(triplet.get("query", "")).strip()
        positive_id = str(triplet.get("positive_chunk_id", "")).strip()
        negative_id = str(triplet.get("negative_chunk_id", "")).strip()
        if not query or not positive_id or not negative_id:
            raise ValueError(f"Triplet row {row_number} is missing query or chunk IDs")
        if positive_id not in by_id or negative_id not in by_id:
            missing = [value for value in (positive_id, negative_id) if value not in by_id]
            raise ValueError(f"Triplet row {row_number} references missing chunks: {missing}")
        queries.add(query)
        for chunk_id, label in ((positive_id, 1.0), (negative_id, 0.0)):
            key = (query, by_id[chunk_id].text)
            previous = labels.get(key)
            if previous is not None and previous != label:
                raise ValueError(f"Conflicting labels for query/chunk pair on row {row_number}")
            labels[key] = label
    pairs = [
        {"query": query, "text": text, "label": label}
        for (query, text), label in labels.items()
    ]
    positives = sum(pair["label"] == 1.0 for pair in pairs)
    summary = {
        "triplets": len(triplets),
        "queries": len(queries),
        "pairs": len(pairs),
        "positive_pairs": positives,
        "negative_pairs": len(pairs) - positives,
    }
    return pairs, summary


def train_cross_encoder(
    pairs: list[dict],
    output_dir: str | Path,
    *,
    model_name: str = "intfloat/multilingual-e5-small",
    device: str | None = None,
    batch_size: int = 8,
    epochs: int = 1,
    learning_rate: float = 2e-5,
    seed: int = 42,
    local_files_only: bool = False,
) -> dict:
    """Fine-tune a binary cross-encoder and persist its checkpoint and run metadata."""
    if not pairs:
        raise ValueError("Reranker training requires at least one labeled pair")
    if batch_size < 1 or epochs < 1 or learning_rate <= 0:
        raise ValueError("batch_size, epochs, and learning_rate must be positive")
    try:
        import torch
        from sentence_transformers import CrossEncoder, InputExample
        from torch.utils.data import DataLoader
    except ImportError as exc:
        raise RuntimeError(
            'Reranker training requires the optional dependency: pip install -e ".[vision]"'
        ) from exc
    random.seed(seed)
    torch.manual_seed(seed)
    examples = [
        InputExample(texts=[pair["query"], pair["text"]], label=float(pair["label"]))
        for pair in pairs
    ]
    generator = torch.Generator().manual_seed(seed)
    loader = DataLoader(examples, shuffle=True, batch_size=batch_size, generator=generator)
    model = CrossEncoder(
        model_name,
        num_labels=1,
        device=device,
        local_files_only=local_files_only,
    )
    steps = math.ceil(len(examples) / batch_size) * epochs
    warmup_steps = max(1, math.ceil(steps * 0.1))
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    model.old_fit(
        train_dataloader=loader,
        epochs=epochs,
        warmup_steps=warmup_steps,
        optimizer_params={"lr": learning_rate},
        output_path=str(target),
        save_best_model=False,
        show_progress_bar=True,
    )
    model.save(str(target))
    summary = {
        "model": model_name,
        "device": str(model.device),
        "pairs": len(pairs),
        "batch_size": batch_size,
        "epochs": epochs,
        "learning_rate": learning_rate,
        "seed": seed,
        "training_steps": steps,
        "warmup_steps": warmup_steps,
        "output_dir": str(target),
    }
    (target / "slide2study_training.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


class CrossEncoderReranker(Reranker):
    """SentenceTransformers cross-encoder adapter for ranked chunk candidates."""

    def __init__(self, model_name_or_path: str | Path, device: str | None = None):
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError(
                'Cross-encoder inference requires: pip install -e ".[vision]"'
            ) from exc
        self.model = CrossEncoder(str(model_name_or_path), device=device)

    def rerank(self, query: str, candidates: list[SearchResult]) -> list[SearchResult]:
        if not candidates:
            return []
        scores = self.model.predict(
            [[query, candidate.chunk.text] for candidate in candidates],
            show_progress_bar=False,
        )
        ordered = sorted(zip(candidates, scores, strict=True), key=lambda item: -float(item[1]))
        return [
            SearchResult(chunk=candidate.chunk, score=float(score), rank=rank)
            for rank, (candidate, score) in enumerate(ordered, 1)
        ]


class RerankedRetriever:
    """Retrieve a wider candidate set, then reorder it with a cross-encoder."""

    def __init__(self, retriever: Retriever, reranker: Reranker, candidate_k: int = 20):
        if candidate_k < 1:
            raise ValueError("candidate_k must be positive")
        self.retriever = retriever
        self.reranker = reranker
        self.candidate_k = candidate_k

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        candidates = self.retriever.search(query, max(top_k, self.candidate_k))
        return self.reranker.rerank(query, candidates)[:top_k]
