"""Protocol boundaries for future CLI-to-service adapters.

No existing CLI is redirected through these ports yet.  Keeping the protocol
separate lets later changes preserve current argparse and output behavior.
"""

from __future__ import annotations

from typing import Protocol

from ramp_core.pipeline.contracts import ArtifactRef, StageRequest, StageResult


class ArtifactResolver(Protocol):
    """Read a named artifact reference without exposing storage details."""

    def resolve(self, artifact: ArtifactRef) -> ArtifactRef:
        """Return the resolved artifact with its available lineage metadata."""


class StageService(Protocol):
    """Execute one declared workflow stage behind an eventual CLI adapter."""

    def run(self, request: StageRequest) -> StageResult:
        """Run a request while preserving its declared output contract."""
