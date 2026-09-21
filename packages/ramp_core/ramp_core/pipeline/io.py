"""Small file-lineage helpers for the workflow contracts.

These helpers are read-only.  They intentionally do not rewrite historical
HDF5 files, manifests, checkpoints, or final evidence.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from ramp_core.pipeline.contracts import ArtifactKind, ArtifactRef


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest of an existing regular file."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not path.is_file():
        raise FileNotFoundError(f"artifact file does not exist: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_from_file(*, root: Path, path: Path, kind: ArtifactKind) -> ArtifactRef:
    """Describe a file below *root* using a portable relative path and digest."""

    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise ValueError("artifact path must be inside the declared repository root") from error
    return ArtifactRef(kind=kind, path=relative.as_posix(), sha256=sha256_file(path))
