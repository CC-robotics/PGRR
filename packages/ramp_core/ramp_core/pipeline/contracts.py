"""Typed, ROS-independent contracts for workflow artifacts and stages.

The contracts are intentionally small: existing command-line scripts can
adopt them incrementally while retaining their current arguments and output
formats.  They do not alter any recovery decision, learning label, benchmark,
or published artifact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ArtifactKind(str, Enum):
    """The workflow artifacts whose lineage must remain explicit."""

    SCENARIO_MANIFEST = "scenario_manifest"
    EPISODE_METADATA = "episode_metadata"
    EPISODE_STREAM = "episode_stream"
    EPISODE_OUTCOME = "episode_outcome"
    EXPERT_HDF5 = "expert_hdf5"
    CHECKPOINT = "checkpoint"
    EVALUATION_TASK = "evaluation_task"
    RUN_ARTIFACT = "run_artifact"


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """A repository-relative workflow artifact with an optional SHA-256.

    Relative paths make manifests portable between the offline and online
    environments.  A digest is optional for a draft request but, when known,
    must be a normalized 64-character SHA-256 value.
    """

    kind: ArtifactKind
    path: str
    sha256: str | None = None

    def __post_init__(self) -> None:
        normalized = self.path.replace("\\", "/")
        candidate = PurePosixPath(normalized)
        if not normalized or candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("artifact path must be a non-empty repository-relative path")
        if str(candidate) in {".", ""}:
            raise ValueError("artifact path must name a file")
        object.__setattr__(self, "path", candidate.as_posix())
        if self.sha256 is not None:
            digest = self.sha256.lower()
            if not _SHA256_RE.fullmatch(digest):
                raise ValueError("sha256 must be a 64-character hexadecimal digest")
            object.__setattr__(self, "sha256", digest)


@dataclass(frozen=True, slots=True)
class StageRequest:
    """Inputs and declared outputs for one reproducible workflow stage."""

    name: str
    inputs: tuple[ArtifactRef, ...]
    outputs: tuple[ArtifactRef, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("stage name must be non-empty")
        if not self.outputs:
            raise ValueError("stage must declare at least one output artifact")
        output_paths = [artifact.path for artifact in self.outputs]
        if len(output_paths) != len(set(output_paths)):
            raise ValueError("stage outputs must have distinct paths")


@dataclass(frozen=True, slots=True)
class StageResult:
    """A stage completion record suitable for a future CLI adapter."""

    request: StageRequest
    produced: tuple[ArtifactRef, ...]
    message: str = ""

    def __post_init__(self) -> None:
        declared = {artifact.path for artifact in self.request.outputs}
        actual = {artifact.path for artifact in self.produced}
        if actual != declared:
            raise ValueError("produced artifacts must match declared stage outputs")
