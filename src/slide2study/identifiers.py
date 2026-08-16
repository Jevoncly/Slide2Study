from __future__ import annotations

import hashlib
from pathlib import Path


def stable_document_id(path: str | Path) -> str:
    """Return a rename-independent ID derived from the complete source bytes."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Document does not exist: {source}")
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"doc-{digest.hexdigest()[:16]}"
