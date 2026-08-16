from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

from slide2study.identifiers import stable_document_id
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
    document_id = stable_document_id(source)
    suffix = source.suffix.lower()
    if suffix == ".pdf":
        return _render_pdf(
            source,
            target,
            source,
            document_id,
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
                document_id,
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

    def __init__(
        self,
        model_name: str = "clip-ViT-B-32",
        device: str | None = None,
        batch_size: int = 16,
    ):
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Visual encoding requires: pip install 'slide2study[vision]'"
            ) from exc
        self.model_name = model_name
        self.batch_size = batch_size
        self.model = SentenceTransformer(model_name, device=device)

    def encode_pages(self, image_paths: list[str]) -> list[list[float]]:
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError(
                "Visual encoding requires: pip install 'slide2study[vision]'"
            ) from exc
        vectors = []
        for offset in range(0, len(image_paths), self.batch_size):
            images = []
            for path in image_paths[offset : offset + self.batch_size]:
                with Image.open(path) as image:
                    images.append(image.convert("RGB").copy())
            encoded = self.model.encode(
                images,
                batch_size=self.batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            vectors.extend(_as_float_vectors(encoded))
        return vectors

    def encode_queries(self, queries: list[str]) -> list[list[float]]:
        return _as_float_vectors(
            self.model.encode(
                queries,
                batch_size=self.batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        )


def write_page_embedding_cache(
    pages: Sequence[RenderedPage],
    embeddings: Sequence[Sequence[float]],
    path: str | Path,
    model_name: str,
) -> None:
    vectors = _validate_and_normalize(embeddings, len(pages))
    payload = {
        "format": "slide2study-page-embeddings-v1",
        "model": model_name,
        "dimensions": len(vectors[0]) if vectors else 0,
        "pages": [
            {
                "document_id": page.document_id,
                "page_number": page.page_number,
                "image_sha256": page.sha256,
                "embedding": vector,
            }
            for page, vector in zip(pages, vectors)
        ],
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")


def load_page_embedding_cache(
    pages: Sequence[RenderedPage], path: str | Path, model_name: str | None = None
) -> tuple[list[list[float]], str]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("format") != "slide2study-page-embeddings-v1":
        raise ValueError("Unsupported page embedding cache format")
    cached_model = payload.get("model")
    if not isinstance(cached_model, str) or not cached_model:
        raise ValueError("Page embedding cache has no model name")
    if model_name is not None and cached_model != model_name:
        raise ValueError(f"Embedding cache model is {cached_model!r}, expected {model_name!r}")
    records = {
        (record.get("document_id"), record.get("page_number")): record
        for record in payload.get("pages", [])
    }
    vectors = []
    for page in pages:
        key = (page.document_id, page.page_number)
        record = records.get(key)
        if record is None:
            raise ValueError(
                f"Embedding cache is missing page {page.document_id} p.{page.page_number}"
            )
        if record.get("image_sha256") != page.sha256:
            raise ValueError(
                f"Embedding cache image mismatch for {page.document_id} p.{page.page_number}"
            )
        vectors.append(record.get("embedding"))
    return _validate_and_normalize(vectors, len(pages)), cached_model


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
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        return _render_pdf_with_poppler(
            pdf_path,
            target_dir,
            source_path,
            document_id,
            dpi,
            executable,
            page_metadata,
        )
    except RuntimeError as poppler_error:
        try:
            return _render_pdf_with_pymupdf(
                pdf_path,
                target_dir,
                source_path,
                document_id,
                dpi,
                page_metadata,
            )
        except RuntimeError as pymupdf_error:
            raise RuntimeError(
                "PDF rendering failed with both Poppler and PyMuPDF. "
                f"Poppler: {poppler_error} PyMuPDF: {pymupdf_error}"
            ) from pymupdf_error


def _render_pdf_with_poppler(
    pdf_path: Path,
    target_dir: Path,
    source_path: Path,
    document_id: str,
    dpi: int,
    executable: str | Path | None,
    page_metadata: dict[int, dict[str, object]],
) -> list[RenderedPage]:
    pdftoppm = _resolve_executable(executable, "pdftoppm")
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
            pages.append(
                _rendered_page(
                    destination,
                    source_path,
                    document_id,
                    page_number,
                    page_metadata,
                )
            )
    return pages


def _render_pdf_with_pymupdf(
    pdf_path: Path,
    target_dir: Path,
    source_path: Path,
    document_id: str,
    dpi: int,
    page_metadata: dict[int, dict[str, object]],
) -> list[RenderedPage]:
    try:
        import pymupdf
    except ImportError as exc:
        raise RuntimeError(
            "PyMuPDF is not installed: pip install 'slide2study[documents]'"
        ) from exc

    document = None
    try:
        document = pymupdf.open(pdf_path)
        if document.page_count < 1:
            raise RuntimeError("PyMuPDF found no pages in the PDF")
        scale = dpi / 72
        matrix = pymupdf.Matrix(scale, scale)
        pages = []
        for page_number, page in enumerate(document, 1):
            destination = target_dir / f"page-{page_number:04d}.png"
            page.get_pixmap(matrix=matrix, alpha=False).save(destination)
            pages.append(
                _rendered_page(
                    destination,
                    source_path,
                    document_id,
                    page_number,
                    page_metadata,
                )
            )
        return pages
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"PyMuPDF command failed: {exc}") from exc
    finally:
        if document is not None:
            document.close()


def _rendered_page(
    destination: Path,
    source_path: Path,
    document_id: str,
    page_number: int,
    page_metadata: dict[int, dict[str, object]],
) -> RenderedPage:
    width, height = _image_size(destination)
    metadata = page_metadata.get(page_number, {})
    return RenderedPage(
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
