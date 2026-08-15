from __future__ import annotations

import hashlib
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence

from slide2study.interfaces import MultimodalPageEncoder
from slide2study.io import read_jsonl, write_jsonl
from slide2study.models import PageSearchResult, RenderedPage


def render_document(
    path: str | Path,
    output_dir: str | Path,
    *,
    dpi: int = 144,
    pdftoppm_executable: str | Path | None = None,
    soffice_executable: str | Path | None = None,
    page_metadata: dict[int, dict[str, object]] | None = None,
) -> list[RenderedPage]:
    """Render PDF/PPTX pages to stable PNG files and return their evidence mapping."""
    source = Path(path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Document does not exist: {source}")
    if dpi <= 0:
        raise ValueError("dpi must be positive")
    target = Path(output_dir).resolve() / source.stem
    suffix = source.suffix.lower()
    if suffix == ".pdf":
        return _render_pdf(
            source,
            target,
            source,
            source.stem,
            dpi,
            pdftoppm_executable,
            page_metadata or {},
        )
    if suffix == ".pptx":
        soffice = _resolve_executable(soffice_executable, "soffice")
        with tempfile.TemporaryDirectory(prefix="slide2study-pptx-") as directory:
            converted_dir = Path(directory)
            _run(
                [
                    str(soffice),
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(converted_dir),
                    str(source),
                ]
            )
            converted = converted_dir / f"{source.stem}.pdf"
            if not converted.is_file():
                raise RuntimeError("LibreOffice did not produce the expected PDF")
            return _render_pdf(
                converted,
                target,
                source,
                source.stem,
                dpi,
                pdftoppm_executable,
                page_metadata or {},
            )
    raise ValueError(f"Visual rendering supports PDF and PPTX, not {suffix or '<none>'}")


def write_page_manifest(pages: Sequence[RenderedPage], path: str | Path) -> None:
    write_jsonl((page.to_dict() for page in pages), path)


def load_page_manifest(path: str | Path) -> list[RenderedPage]:
    return [RenderedPage.from_dict(row) for row in read_jsonl(path)]


class SentenceTransformersCLIPEncoder(MultimodalPageEncoder):
    """Pretrained cross-modal baseline using the SentenceTransformers CLIP model."""

    def __init__(self, model_name: str = "clip-ViT-B-32", device: str | None = None):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Visual encoding requires: pip install 'slide2study[vision]'"
            ) from exc
        self.model_name = model_name
        self.model = SentenceTransformer(model_name, device=device)

    def encode_pages(self, image_paths: list[str]) -> list[list[float]]:
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError(
                "Visual encoding requires: pip install 'slide2study[vision]'"
            ) from exc
        images = []
        for path in image_paths:
            with Image.open(path) as image:
                images.append(image.convert("RGB").copy())
        return _as_float_vectors(
            self.model.encode(images, normalize_embeddings=True, show_progress_bar=False)
        )

    def encode_queries(self, queries: list[str]) -> list[list[float]]:
        return _as_float_vectors(
            self.model.encode(queries, normalize_embeddings=True, show_progress_bar=False)
        )


class VisualPageRetriever:
    """Cosine-similarity query-to-page retrieval over cross-modal embeddings."""

    def __init__(
        self,
        pages: Sequence[RenderedPage],
        encoder: MultimodalPageEncoder,
        page_embeddings: Sequence[Sequence[float]] | None = None,
    ):
        self.pages = list(pages)
        self.encoder = encoder
        vectors = page_embeddings
        if vectors is None:
            vectors = encoder.encode_pages([page.image_path for page in self.pages])
        self.page_embeddings = _validate_and_normalize(vectors, len(self.pages))

    def search(self, query: str, top_k: int = 5) -> list[PageSearchResult]:
        if top_k <= 0:
            return []
        query_vectors = self.encoder.encode_queries([query])
        query_vector = _validate_and_normalize(query_vectors, 1)[0]
        if self.page_embeddings and len(query_vector) != len(self.page_embeddings[0]):
            raise ValueError("Query and page embeddings must have the same dimensions")
        scored = [
            (sum(left * right for left, right in zip(query_vector, vector)), index)
            for index, vector in enumerate(self.page_embeddings)
        ]
        scored.sort(key=lambda item: (-item[0], self.pages[item[1]].page_number))
        return [
            PageSearchResult(self.pages[index], round(score, 8), rank)
            for rank, (score, index) in enumerate(scored[:top_k], 1)
        ]


def _render_pdf(
    pdf_path: Path,
    target_dir: Path,
    source_path: Path,
    document_id: str,
    dpi: int,
    executable: str | Path | None,
    page_metadata: dict[int, dict[str, object]],
) -> list[RenderedPage]:
    pdftoppm = _resolve_executable(executable, "pdftoppm")
    target_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="slide2study-render-") as directory:
        prefix = Path(directory) / "rendered"
        _run([str(pdftoppm), "-png", "-r", str(dpi), str(pdf_path), str(prefix)])
        rendered = sorted(
            Path(directory).glob("rendered-*.png"), key=_rendered_page_number
        )
        if not rendered:
            raise RuntimeError("pdftoppm produced no page images")
        pages = []
        for page_number, temporary in enumerate(rendered, 1):
            destination = target_dir / f"page-{page_number:04d}.png"
            shutil.copy2(temporary, destination)
            width, height = _image_size(destination)
            metadata = page_metadata.get(page_number, {})
            pages.append(
                RenderedPage(
                    document_id=document_id,
                    page_number=page_number,
                    image_path=str(destination),
                    source_path=str(source_path),
                    width=width,
                    height=height,
                    sha256=_sha256(destination),
                    requires_vision=bool(metadata.get("requires_vision", False)),
                    role=str(metadata.get("role", "content")),
                    visual_risk_score=float(metadata.get("visual_risk_score", 0.0)),
                )
            )
    return pages


def _resolve_executable(explicit: str | Path | None, name: str) -> Path:
    value = str(explicit) if explicit else shutil.which(name)
    if not value:
        extra = " Install LibreOffice." if name == "soffice" else " Install Poppler."
        raise RuntimeError(f"Required executable was not found: {name}.{extra}")
    resolved = Path(value)
    if not resolved.is_file():
        raise RuntimeError(f"Required executable does not exist: {resolved}")
    return resolved


def _run(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except OSError as exc:
        raise RuntimeError(f"Could not start executable: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"Command failed: {message}") from exc


def _rendered_page_number(path: Path) -> int:
    match = re.search(r"-(\d+)\.png$", path.name)
    return int(match.group(1)) if match else 0


def _image_size(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "Page rendering requires Pillow: pip install 'slide2study[vision]'"
        ) from exc
    with Image.open(path) as image:
        return image.size


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _as_float_vectors(values: object) -> list[list[float]]:
    raw = values.tolist() if hasattr(values, "tolist") else values
    return [[float(item) for item in vector] for vector in raw]  # type: ignore[union-attr]


def _validate_and_normalize(
    vectors: Sequence[Sequence[float]], expected_count: int
) -> list[list[float]]:
    if len(vectors) != expected_count:
        raise ValueError(f"Expected {expected_count} embedding(s), received {len(vectors)}")
    if not vectors:
        return []
    dimensions = {len(vector) for vector in vectors}
    if len(dimensions) != 1 or 0 in dimensions:
        raise ValueError("Embeddings must be non-empty and have consistent dimensions")
    normalized = []
    for vector in vectors:
        norm = math.sqrt(sum(float(value) ** 2 for value in vector))
        if norm == 0:
            raise ValueError("Embedding vectors must have non-zero norm")
        normalized.append([float(value) / norm for value in vector])
    return normalized
