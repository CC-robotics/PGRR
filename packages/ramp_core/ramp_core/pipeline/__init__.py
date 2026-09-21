"""Stable artifact and stage interfaces for PGRR workflow tooling.

This package deliberately describes workflow inputs and outputs without
changing recovery, training, ROS, or published-release behavior.
"""

from ramp_core.pipeline.contracts import ArtifactKind, ArtifactRef, StageRequest, StageResult

__all__ = ["ArtifactKind", "ArtifactRef", "StageRequest", "StageResult"]
