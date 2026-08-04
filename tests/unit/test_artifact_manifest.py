from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/paper/build_artifact_manifest.py"
SPEC = importlib.util.spec_from_file_location("build_artifact_manifest", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _write(path: Path, content: bytes = b"artifact\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _complete_fixture(root: Path) -> None:
    for relative in (
        MODULE.DEFAULT_CONFIG,
        MODULE.DEFAULT_CHECKPOINT,
        MODULE.DEFAULT_RESULTS,
        MODULE.DEFAULT_SUMMARY,
        MODULE.DEFAULT_STATISTICS,
        MODULE.DEFAULT_FAILURE_ANALYSIS,
        MODULE.DEFAULT_EPISODE_MANIFEST,
        MODULE.DEFAULT_RUN_MANIFEST,
        MODULE.DEFAULT_OFFLINE_ABLATION_CSV,
        MODULE.DEFAULT_OFFLINE_ABLATION_JSON,
        MODULE.DEFAULT_PAPER,
        MODULE.DEFAULT_MAIN_TEX,
        MODULE.DEFAULT_REFERENCES,
        MODULE.DEFAULT_CLAIM_MATRIX,
        MODULE.DEFAULT_ENVIRONMENT_LOCK,
        MODULE.DEFAULT_REQUIREMENTS_LOCK,
        MODULE.DEFAULT_ARENA_LOCK,
        MODULE.DEFAULT_DEPENDENCY_MANIFEST,
        MODULE.DEFAULT_TEST_SPLIT,
        MODULE.DEFAULT_FAILURE_CONFIG,
        MODULE.DEFAULT_STATE_MACHINE_CONFIG,
        MODULE.DEFAULT_ACTION_CONFIG,
    ):
        _write(root / relative)
    _write(root / "paper/sections/method.tex", b"section\n")
    for name in MODULE.EXPECTED_FIGURES:
        _write(root / MODULE.DEFAULT_FIGURES_DIR / name, b"%PDF figure\n")
        _write(root / MODULE.DEFAULT_OUTPUT_FIGURES_DIR / name, b"%PDF figure\n")
    for name in MODULE.EXPECTED_TABLES:
        _write(root / MODULE.DEFAULT_TABLES_DIR / name, b"table\n")
        _write(root / MODULE.DEFAULT_OUTPUT_TABLES_DIR / name, b"table\n")
    _write(root / MODULE.DEFAULT_VIDEOS_DIR / "representative_telemetry.mp4", b"video\n")
    _write(
        root / MODULE.DEFAULT_OUTPUT_FIGURES_DIR / "representative_telemetry_keyframes.pdf",
        b"%PDF keyframes\n",
    )
    _write(
        root / MODULE.DEFAULT_OUTPUT_FIGURES_DIR / "representative_telemetry_keyframes.png",
        b"PNG keyframes\n",
    )


def test_manifest_has_only_relative_checksummed_artifacts(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)

    payload = MODULE.build_manifest(
        tmp_path,
        generation_command="scripts/reproduce_paper.sh",
        generated_at="2026-08-04T12:00:00+00:00",
        project_commit="a" * 40,
        git_dirty=False,
    )

    assert payload["schema_version"] == 1
    assert payload["project_commit"] == "a" * 40
    assert payload["git_worktree_dirty"] is False
    assert payload["category_counts"]["figure"] == len(MODULE.EXPECTED_FIGURES)
    assert payload["category_counts"]["table"] == len(MODULE.EXPECTED_TABLES)
    assert payload["category_counts"]["video"] == 1
    assert payload["category_counts"]["runtime_keyframe"] == 2
    assert payload["artifact_count"] == len(payload["artifacts"])
    paths = {record["path"] for record in payload["artifacts"]}
    assert MODULE.DEFAULT_PAPER.as_posix() in paths
    assert all(not Path(path).is_absolute() for path in paths)
    checkpoint = tmp_path / MODULE.DEFAULT_CHECKPOINT
    record = next(
        item
        for item in payload["artifacts"]
        if item["path"] == MODULE.DEFAULT_CHECKPOINT.as_posix()
    )
    assert record["sha256"] == hashlib.sha256(checkpoint.read_bytes()).hexdigest()


def test_manifest_fails_closed_when_a_required_artifact_is_missing(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    (tmp_path / MODULE.DEFAULT_PAPER).unlink()

    with pytest.raises(MODULE.ArtifactError, match="paper PDF"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="b" * 40,
            git_dirty=True,
        )


def test_manifest_requires_a_final_telemetry_video(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    (tmp_path / MODULE.DEFAULT_VIDEOS_DIR / "representative_telemetry.mp4").unlink()

    with pytest.raises(MODULE.ArtifactError, match="final telemetry video"):
        MODULE.build_manifest(
            tmp_path,
            project_commit="c" * 40,
            git_dirty=True,
        )


def test_manifest_rejects_artifacts_outside_project(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    outside = tmp_path.parent / "outside.pdf"
    _write(outside)

    with pytest.raises(MODULE.ArtifactError, match="inside the project root"):
        MODULE.build_manifest(
            tmp_path,
            paper_path=outside,
            project_commit="d" * 40,
            git_dirty=True,
        )
