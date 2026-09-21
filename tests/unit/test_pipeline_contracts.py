from __future__ import annotations

from pathlib import Path

import pytest
from ramp_core.pipeline.contracts import (
    ArtifactKind,
    ArtifactRef,
    StageRequest,
    StageResult,
)
from ramp_core.pipeline.io import artifact_from_file, sha256_file


def _output(path: str = "outputs/student/example.json") -> ArtifactRef:
    return ArtifactRef(ArtifactKind.RUN_ARTIFACT, path)


def test_artifact_reference_normalizes_portable_path_and_digest() -> None:
    artifact = ArtifactRef(
        ArtifactKind.CHECKPOINT,
        r"checkpoints\\student\\best.onnx",
        "A" * 64,
    )
    assert artifact.path == "checkpoints/student/best.onnx"
    assert artifact.sha256 == "a" * 64


@pytest.mark.parametrize("path", ("", ".", "../outside.json", "/absolute.json"))
def test_artifact_reference_rejects_nonportable_paths(path: str) -> None:
    with pytest.raises(ValueError, match="artifact path"):
        ArtifactRef(ArtifactKind.RUN_ARTIFACT, path)


def test_stage_requires_distinct_declared_outputs() -> None:
    with pytest.raises(ValueError, match="distinct"):
        StageRequest("collect", (), (_output(), _output()))


def test_stage_result_requires_exact_declared_outputs() -> None:
    request = StageRequest("collect", (), (_output(),))
    with pytest.raises(ValueError, match="match"):
        StageResult(request, ())


def test_file_artifact_captures_relative_path_and_digest(tmp_path: Path) -> None:
    root = tmp_path / "project"
    file_path = root / "data" / "episode.json"
    file_path.parent.mkdir(parents=True)
    file_path.write_text('{"episode": 1}\n', encoding="utf-8")

    artifact = artifact_from_file(
        root=root,
        path=file_path,
        kind=ArtifactKind.EPISODE_METADATA,
    )

    assert artifact.path == "data/episode.json"
    assert artifact.sha256 == sha256_file(file_path)


def test_file_artifact_rejects_file_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="inside"):
        artifact_from_file(root=root, path=outside, kind=ArtifactKind.RUN_ARTIFACT)
