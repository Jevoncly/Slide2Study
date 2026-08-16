from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from slide2study.models import Chunk
from slide2study.retrieval import _validate_and_normalize


class SentenceTransformersTextEncoder:
    """SentenceTransformers baseline for asymmetric multilingual retrieval."""

    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-small",
        device: str | None = None,
        batch_size: int = 32,
        query_prefix: str = "query: ",
        document_prefix: str = "passage: ",
    ):
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Dense encoding requires: pip install 'slide2study[vision]'"
            ) from exc
        self.model_name = model_name
        self.batch_size = batch_size
        self.query_prefix = query_prefix
        self.document_prefix = document_prefix
        self.model = SentenceTransformer(model_name, device=device)

    def encode_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode([self.document_prefix + text for text in texts])

    def encode_queries(self, queries: list[str]) -> list[list[float]]:
        return self._encode([self.query_prefix + query for query in queries])

    def _encode(self, texts: list[str]) -> list[list[float]]:
        encoded = self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [[float(value) for value in vector] for vector in encoded]


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_chunk_embedding_cache(
    chunks: Sequence[Chunk],
    embeddings: Sequence[Sequence[float]],
    path: str | Path,
    model_name: str,
    query_prefix: str,
    document_prefix: str,
) -> None:
    vectors = _validate_and_normalize(embeddings, len(chunks))
    payload = {
        "format": "slide2study-chunk-embeddings-v1",
        "model": model_name,
        "query_prefix": query_prefix,
        "document_prefix": document_prefix,
        "dimensions": len(vectors[0]) if vectors else 0,
        "chunks": [
            {
                "chunk_id": chunk.chunk_id,
                "text_sha256": _text_sha256(chunk.text),
                "embedding": vector,
            }
            for chunk, vector in zip(chunks, vectors)
        ],
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")


def load_chunk_embedding_cache(
    chunks: Sequence[Chunk], path: str | Path, model_name: str | None = None
) -> tuple[list[list[float]], dict[str, str]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("format") != "slide2study-chunk-embeddings-v1":
        raise ValueError("Unsupported chunk embedding cache format")
    cached_model = payload.get("model")
    if not isinstance(cached_model, str) or not cached_model:
        raise ValueError("Chunk embedding cache has no model name")
    if model_name is not None and cached_model != model_name:
        raise ValueError(f"Embedding cache model is {cached_model!r}, expected {model_name!r}")
    records = {record.get("chunk_id"): record for record in payload.get("chunks", [])}
    if len(records) != len(payload.get("chunks", [])):
        raise ValueError("Chunk embedding cache contains duplicate chunk IDs")
    vectors = []
    for chunk in chunks:
        record = records.get(chunk.chunk_id)
        if record is None:
            raise ValueError(f"Embedding cache is missing chunk {chunk.chunk_id}")
        if record.get("text_sha256") != _text_sha256(chunk.text):
            raise ValueError(f"Embedding cache text mismatch for chunk {chunk.chunk_id}")
        vectors.append(record.get("embedding"))
    metadata = {
        "model": cached_model,
        "query_prefix": str(payload.get("query_prefix", "")),
        "document_prefix": str(payload.get("document_prefix", "")),
    }
    return _validate_and_normalize(vectors, len(chunks)), metadata
