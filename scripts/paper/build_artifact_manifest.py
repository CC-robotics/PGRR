#!/usr/bin/env python3
"""Build a checksummed manifest for the reproducible paper artifacts.

All stored paths are relative to the repository root derived from this file.
The command fails closed when a declared publication artifact is missing or
empty; it never invents results or silently omits an artifact category.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CONFIG = Path("configs/experiments/scenario_catalog_moderate_v6.yaml")
DEFAULT_EVALUATION_CONFIG = Path("configs/final/ei_gazebo.yaml")
DEFAULT_BASELINE_CONFIG = Path("configs/planner/baselines.yaml")
DEFAULT_UNIFORM_CHECKPOINT = Path("checkpoints/bc/uniform_scenario/best.onnx")
DEFAULT_CHECKPOINT = Path("checkpoints/dagger/coverage_safety_aligned/best.onnx")
DEFAULT_RESULTS = Path("outputs/moderate/final/results.parquet")
DEFAULT_SUMMARY = Path("outputs/moderate/final/summary.csv")
DEFAULT_STATISTICS = Path("outputs/moderate/final/pairwise_statistics.json")
DEFAULT_CALIBRATION_SPLIT = Path("scenarios/splits/moderate_v6_validation.yaml")
DEFAULT_CALIBRATION_REPORT = Path(
    "outputs/moderate/v6_validation_base_d5fa66b/calibration_report.json"
)
DEFAULT_FAILURE_ANALYSIS = Path("outputs/moderate/final/failure_analysis.md")
DEFAULT_EPISODE_MANIFEST = Path("outputs/moderate/final/episode_manifest.parquet")
DEFAULT_RUN_MANIFEST = Path("outputs/moderate/final/run_manifest.json")
DEFAULT_OFFLINE_ABLATION_CSV = Path("outputs/moderate/final/offline_policy_ablation.csv")
DEFAULT_OFFLINE_ABLATION_JSON = Path("outputs/moderate/final/offline_policy_ablation.json")
DEFAULT_OFFLINE_ABLATION_DATASET = Path("data/interim/multiscenario_safety_aligned_validation.h5")
DEFAULT_FIGURES_DIR = Path("paper/figures")
DEFAULT_TABLES_DIR = Path("paper/generated")
DEFAULT_OUTPUT_FIGURES_DIR = Path("outputs/figures")
DEFAULT_OUTPUT_TABLES_DIR = Path("outputs/tables")
DEFAULT_MEDIA_KEYFRAMES_PDF = Path(
    "outputs/moderate/final/media/pgrr_representative_telemetry_keyframes.pdf"
)
DEFAULT_MEDIA_KEYFRAMES_PNG = Path(
    "outputs/moderate/final/media/pgrr_representative_telemetry_keyframes.png"
)
DEFAULT_VIDEO = Path("outputs/moderate/final/media/pgrr_representative_telemetry.mp4")
DEFAULT_PAPER = Path("paper/main.pdf")
DEFAULT_REPORT = Path("report/PGRR_technical_report_zh.pdf")
DEFAULT_REPORT_DATA = Path("report/generated/report_data.json")
DEFAULT_PRESENTATION_PPTX = Path("presentation/PGRR_report_zh.pptx")
DEFAULT_PRESENTATION_PDF = Path("presentation/PGRR_report_zh.pdf")
DEFAULT_PRESENTATION_NOTES = Path("presentation/speaker_notes_zh.md")
DEFAULT_PRESENTATION_CONTACT_SHEET = Path("presentation/contact_sheet.png")
DEFAULT_MAIN_TEX = Path("paper/main.tex")
DEFAULT_REFERENCES = Path("paper/references.bib")
DEFAULT_CLAIM_MATRIX = Path("paper/claim_evidence_matrix.md")
DEFAULT_ENVIRONMENT_LOCK = Path("environment.lock.yml")
DEFAULT_REQUIREMENTS_LOCK = Path("requirements-offline.lock.txt")
DEFAULT_ARENA_LOCK = Path("third_party/arena_commits.lock")
DEFAULT_DEPENDENCY_MANIFEST = Path("third_party/dependency_manifest.md")
DEFAULT_TEST_SPLIT = Path("scenarios/splits/moderate_v6_test.yaml")
DEFAULT_FAILURE_CONFIG = Path("configs/failure/rules.yaml")
DEFAULT_STATE_MACHINE_CONFIG = Path("configs/failure/recovery_state_machine.yaml")
DEFAULT_ACTION_CONFIG = Path("configs/planner/recovery_actions.yaml")
DEFAULT_OUTPUT = Path("outputs/moderate/final/artifact_manifest.json")
OPTIONAL_RUNTIME_SCREENSHOT = Path("paper/figures/runtime_gazebo_doorway_bottleneck_medium.png")
OPTIONAL_RUNTIME_SCREENSHOT_SOURCE = Path(
    "outputs/figures/runtime/gazebo_doorway_bottleneck_medium.png"
)
OPTIONAL_RUNTIME_CAPTURE_METADATA = Path(
    "outputs/figures/runtime/gazebo_doorway_bottleneck_medium.metadata.json"
)

COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
ALGORITHM_OUTCOMES = {
    "GOAL_REACHED",
    "COLLISION",
    "TIMEOUT",
    "PLANNER_FAILURE",
}
EXPECTED_BENCHMARK_ID = "moderate_social_navigation_v6"

EXPECTED_FIGURES = (
    "system_architecture.pdf",
    "action_space_expert.pdf",
    "moderate_outcomes_and_density.pdf",
    "moderate_family_success.pdf",
    "moderate_paired_effects.pdf",
    "moderate_safety_efficiency.pdf",
)
EXPECTED_TABLES = (
    "offline_ablation.tex",
    "moderate_main_results.tex",
    "moderate_density_results.tex",
    "moderate_recovery_metrics.tex",
    "moderate_pairwise_statistics.tex",
    "moderate_result_macros.tex",
)


class ArtifactError(RuntimeError):
    """Raised when publication artifacts or their provenance are invalid."""


def sha256_file(path: Path) -> str:
    """Return a streaming SHA256 digest for one file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _inside_root(project_root: Path, value: Path, *, label: str) -> Path:
    candidate = value if value.is_absolute() else project_root / value
    resolved = candidate.resolve()
    try:
        resolved.relative_to(project_root)
    except ValueError as error:
        raise ArtifactError(f"{label} must be inside the project root: {value}") from error
    return resolved


def _require_file(project_root: Path, value: Path, *, label: str) -> Path:
    path = _inside_root(project_root, value, label=label)
    if not path.is_file():
        raise ArtifactError(f"missing required {label}: {path.relative_to(project_root)}")
    if path.stat().st_size <= 0:
        raise ArtifactError(f"empty required {label}: {path.relative_to(project_root)}")
    return path


def _validate_calibration_report(path: Path) -> None:
    """Require an accepted validation-only benchmark calibration report."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ArtifactError(f"invalid calibration report: {path}") from error
    if not isinstance(payload, dict):
        raise ArtifactError("calibration report must contain a JSON object")
    if (
        payload.get("split") != "validation"
        or payload.get("status") != "accepted"
        or payload.get("passed") is not True
    ):
        raise ArtifactError("calibration report must be an accepted validation-only report")


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ArtifactError(f"invalid {label}: {path}") from error
    if not isinstance(payload, dict):
        raise ArtifactError(f"{label} must contain a JSON object: {path}")
    return payload


def _load_yaml_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ArtifactError(f"invalid {label}: {path}") from error
    if not isinstance(payload, dict):
        raise ArtifactError(f"{label} must contain a YAML mapping: {path}")
    return payload


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ArtifactError(f"{label} must be a mapping")
    return value


def _relative(project_root: Path, path: Path) -> str:
    return path.resolve().relative_to(project_root).as_posix()


def _require_sha256(value: object, *, label: str) -> str:
    digest = str(value)
    if SHA256_PATTERN.fullmatch(digest) is None:
        raise ArtifactError(f"{label} must be a lowercase SHA256 digest")
    return digest


def _require_commit(value: object, *, label: str) -> str:
    commit = str(value)
    if COMMIT_PATTERN.fullmatch(commit) is None:
        raise ArtifactError(f"{label} must be a full lowercase Git commit")
    return commit


def _validate_declared_file(
    project_root: Path,
    section: Mapping[str, Any],
    *,
    path_key: str,
    hash_key: str,
    expected_path: Path | None,
    label: str,
) -> Path:
    declared = Path(str(section.get(path_key, "")))
    if not str(declared) or declared.is_absolute():
        raise ArtifactError(f"{label} path must be repository-relative")
    resolved = _require_file(project_root, declared, label=label)
    if expected_path is not None:
        expected = _inside_root(project_root, expected_path, label=label)
        if resolved != expected:
            raise ArtifactError(
                f"{label} path disagrees with the requested artifact: "
                f"{_relative(project_root, resolved)} != {_relative(project_root, expected)}"
            )
    declared_hash = _require_sha256(section.get(hash_key), label=f"{label} hash")
    observed_hash = sha256_file(resolved)
    if observed_hash != declared_hash:
        raise ArtifactError(
            f"{label} hash mismatch: declared {declared_hash}, observed {observed_hash}"
        )
    return resolved


def _read_parquet(path: Path, *, label: str) -> pd.DataFrame:
    try:
        frame = pd.read_parquet(path)
    except (OSError, ValueError) as error:
        raise ArtifactError(f"cannot read {label}: {path}") from error
    if frame.empty:
        raise ArtifactError(f"{label} is empty: {path}")
    return frame


def _require_columns(frame: pd.DataFrame, columns: set[str], *, label: str) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise ArtifactError(f"{label} is missing columns: {', '.join(missing)}")


def _single_string(frame: pd.DataFrame, column: str, *, label: str) -> str:
    values = set(frame[column].fillna("").astype(str))
    if len(values) != 1:
        raise ArtifactError(f"{label} must contain one {column}, found {sorted(values)}")
    return next(iter(values))


def _checkpoint_expectations(
    evaluation_config: Mapping[str, Any],
) -> dict[str, tuple[str, str]]:
    learned_baseline = _mapping(evaluation_config.get("learned_baseline"), label="learned_baseline")
    learned_method = _mapping(evaluation_config.get("learned_method"), label="learned_method")
    return {
        str(learned_baseline.get("source_policy")): (
            str(learned_baseline.get("checkpoint")),
            _require_sha256(
                learned_baseline.get("checkpoint_sha256"),
                label="learned baseline checkpoint hash",
            ),
        ),
        str(learned_method.get("source_policy")): (
            str(learned_method.get("checkpoint")),
            _require_sha256(
                learned_method.get("checkpoint_sha256"),
                label="learned method checkpoint hash",
            ),
        ),
    }


def _validate_evaluation_provenance(
    project_root: Path,
    *,
    config_path: Path,
    evaluation_config_path: Path,
    baseline_config_path: Path,
    uniform_checkpoint_path: Path,
    checkpoint_path: Path,
    results_path: Path,
    calibration_report_path: Path,
    test_split_path: Path,
    episode_manifest_path: Path,
    run_manifest_path: Path,
) -> dict[str, Any]:
    """Cross-check the frozen test configuration and every result provenance layer."""

    evaluation_config_file = _require_file(
        project_root, evaluation_config_path, label="final evaluation configuration"
    )
    evaluation_config = _load_yaml_object(
        evaluation_config_file, label="final evaluation configuration"
    )
    if evaluation_config.get("schema_version") != 2:
        raise ArtifactError("final evaluation configuration must use schema_version 2")

    benchmark = _mapping(evaluation_config.get("benchmark"), label="benchmark")
    runtime = _mapping(evaluation_config.get("runtime"), label="runtime")
    comparison = _mapping(evaluation_config.get("primary_comparison"), label="primary_comparison")
    frozen_inputs = _mapping(evaluation_config.get("frozen_inputs"), label="frozen_inputs")

    catalog = _validate_declared_file(
        project_root,
        benchmark,
        path_key="catalog",
        hash_key="catalog_sha256",
        expected_path=config_path,
        label="benchmark catalog",
    )
    if benchmark.get("id") != EXPECTED_BENCHMARK_ID:
        raise ArtifactError(f"final evaluation benchmark must be {EXPECTED_BENCHMARK_ID}")
    catalog_document = _load_yaml_object(catalog, label="benchmark catalog")
    if catalog_document.get("benchmark_id") != EXPECTED_BENCHMARK_ID:
        raise ArtifactError("benchmark catalog identity disagrees with moderate-v6")
    validation_split = _validate_declared_file(
        project_root,
        benchmark,
        path_key="calibration_split",
        hash_key="calibration_split_sha256",
        expected_path=None,
        label="validation split",
    )
    validation_document = _load_yaml_object(validation_split, label="validation split")
    if (
        validation_document.get("split") != "validation"
        or validation_document.get("benchmark_id") != EXPECTED_BENCHMARK_ID
    ):
        raise ArtifactError("configured calibration split is not a validation split")
    _validate_declared_file(
        project_root,
        benchmark,
        path_key="calibration_report",
        hash_key="calibration_report_sha256",
        expected_path=calibration_report_path,
        label="moderate calibration report",
    )

    if runtime.get("split") != "test":
        raise ArtifactError("final evaluation runtime split must be test")
    test_split = _validate_declared_file(
        project_root,
        runtime,
        path_key="split_manifest",
        hash_key="split_manifest_sha256",
        expected_path=test_split_path,
        label="test split",
    )
    test_document = _load_yaml_object(test_split, label="test split")
    if (
        test_document.get("split") != "test"
        or test_document.get("benchmark_id") != EXPECTED_BENCHMARK_ID
    ):
        raise ArtifactError("configured test split is not a test split")

    frozen_specs = (
        ("arena_profile_sha256", Path("configs/platform/arena_profile.yaml"), "Arena profile"),
        ("planner_profiles_sha256", baseline_config_path, "planner profiles"),
        ("failure_rules_sha256", DEFAULT_FAILURE_CONFIG, "failure rules"),
        ("state_machine_sha256", DEFAULT_STATE_MACHINE_CONFIG, "state machine"),
        ("recovery_actions_sha256", DEFAULT_ACTION_CONFIG, "recovery actions"),
    )
    for hash_key, declared_path, label in frozen_specs:
        resolved = _require_file(project_root, declared_path, label=label)
        declared_hash = _require_sha256(frozen_inputs.get(hash_key), label=f"{label} hash")
        observed_hash = sha256_file(resolved)
        if declared_hash != observed_hash:
            raise ArtifactError(
                f"{label} hash mismatch: declared {declared_hash}, observed {observed_hash}"
            )

    checkpoint_expectations = _checkpoint_expectations(evaluation_config)
    requested_checkpoint_paths = {
        "bc_uniform": _inside_root(
            project_root, uniform_checkpoint_path, label="Uniform BC checkpoint"
        ),
        "pgrr": _inside_root(project_root, checkpoint_path, label="selected checkpoint"),
    }
    if set(checkpoint_expectations) != set(requested_checkpoint_paths):
        raise ArtifactError(
            "final configuration must declare exactly the bc_uniform and pgrr checkpoints"
        )
    for method, (declared_path, declared_hash) in checkpoint_expectations.items():
        checkpoint_file = _require_file(
            project_root, Path(declared_path), label=f"{method} checkpoint"
        )
        if checkpoint_file != requested_checkpoint_paths[method]:
            raise ArtifactError(f"{method} checkpoint path disagrees with artifact arguments")
        observed_hash = sha256_file(checkpoint_file)
        if observed_hash != declared_hash:
            raise ArtifactError(
                f"{method} checkpoint hash mismatch: declared {declared_hash}, "
                f"observed {observed_hash}"
            )

    run_manifest_file = _require_file(project_root, run_manifest_path, label="run manifest")
    run_manifest = _load_json_object(run_manifest_file, label="run manifest")
    if run_manifest.get("schema_version") != 1:
        raise ArtifactError("run manifest must use schema_version 1")
    run_id = str(run_manifest.get("run_id", ""))
    if re.fullmatch(r"[0-9a-f]{12}", run_id) is None:
        raise ArtifactError("run manifest run_id is not a 12-character experiment fingerprint")
    evaluation_commit = _require_commit(
        run_manifest.get("project_commit"), label="run manifest project_commit"
    )
    configured_project_commit = frozen_inputs.get("project_commit")
    if configured_project_commit not in {
        "resolved_and_recorded_by_runner",
        evaluation_commit,
    }:
        raise ArtifactError("final configuration project_commit policy disagrees with runner")

    configured_methods = comparison.get("methods")
    if not isinstance(configured_methods, list) or not all(
        isinstance(method, str) and method for method in configured_methods
    ):
        raise ArtifactError("primary_comparison.methods must be a non-empty string list")
    methods = list(configured_methods)
    if run_manifest.get("methods") != methods or run_manifest.get("high_density_methods") != []:
        raise ArtifactError("run manifest method set/order disagrees with final configuration")
    if run_manifest.get("split") != "test":
        raise ArtifactError("run manifest is not a held-out test run")
    if run_manifest.get("split_manifest") != _relative(project_root, test_split):
        raise ArtifactError("run manifest test split path disagrees with final configuration")
    if run_manifest.get("split_manifest_sha256") != sha256_file(test_split):
        raise ArtifactError("run manifest test split hash disagrees with final configuration")
    episode_manifest_file = _inside_root(
        project_root, episode_manifest_path, label="episode manifest"
    )
    if run_manifest.get("episode_manifest") != _relative(project_root, episode_manifest_file):
        raise ArtifactError("run manifest episode-manifest path disagrees with artifact arguments")
    if float(run_manifest.get("timeout_s", -1.0)) != float(runtime.get("episode_timeout_s", -2.0)):
        raise ArtifactError("run manifest timeout disagrees with final configuration")
    try:
        configured_jobs = int(runtime["parallel_jobs"])
    except (KeyError, TypeError, ValueError) as error:
        raise ArtifactError("final configuration has an invalid parallel_jobs value") from error
    if run_manifest.get("requested_jobs") != configured_jobs:
        raise ArtifactError("run manifest requested_jobs disagrees with final configuration")
    if run_manifest.get("effective_jobs") != configured_jobs:
        raise ArtifactError("run manifest effective_jobs disagrees with final configuration")
    if str(run_manifest.get("recovery_tau_on_override", "")):
        raise ArtifactError("held-out test run must not contain a recovery threshold override")
    if run_manifest.get("worker_errors") != []:
        raise ArtifactError("run manifest contains worker errors")

    try:
        expected_episodes = int(comparison["expected_episodes"])
        expected_per_method = int(comparison["expected_conditions_per_method"])
    except (KeyError, TypeError, ValueError) as error:
        raise ArtifactError("final configuration has invalid expected episode counts") from error
    if expected_episodes != expected_per_method * len(methods):
        raise ArtifactError("configured total episode count disagrees with per-method count")
    scenarios = test_document.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) != expected_per_method:
        raise ArtifactError("test split scenario count disagrees with final configuration")
    configured_families = comparison.get("families")
    configured_densities = comparison.get("densities")
    if not isinstance(configured_families, list) or {
        str(record.get("family")) for record in scenarios if isinstance(record, Mapping)
    } != set(configured_families):
        raise ArtifactError("test split families disagree with final configuration")
    if not isinstance(configured_densities, list) or {
        str(record.get("density")) for record in scenarios if isinstance(record, Mapping)
    } != set(configured_densities):
        raise ArtifactError("test split densities disagree with final configuration")
    try:
        repetitions = int(comparison["repetitions_per_family_density_cell"])
    except (KeyError, TypeError, ValueError) as error:
        raise ArtifactError("final configuration has an invalid repetition count") from error
    if expected_per_method != len(configured_families) * len(configured_densities) * repetitions:
        raise ArtifactError("configured family/density/repetition grid has the wrong size")
    for key in ("expected_task_count", "completed_task_count"):
        if run_manifest.get(key) != expected_episodes:
            raise ArtifactError(f"run manifest {key} disagrees with final configuration")

    run_checkpoints = _mapping(
        run_manifest.get("method_checkpoints"), label="run manifest method_checkpoints"
    )
    if set(run_checkpoints) != set(checkpoint_expectations):
        raise ArtifactError(
            "run manifest learned checkpoint set disagrees with final configuration"
        )
    for method, expected in checkpoint_expectations.items():
        entry = _mapping(run_checkpoints.get(method), label=f"run checkpoint {method}")
        if (str(entry.get("path")), str(entry.get("sha256"))) != expected:
            raise ArtifactError(f"run manifest {method} checkpoint provenance disagrees")

    run_results = run_manifest.get("results")
    if not isinstance(run_results, list) or len(run_results) != expected_episodes:
        raise ArtifactError("run manifest does not contain every completed logical episode")
    task_indices: set[int] = set()
    for record in run_results:
        entry = _mapping(record, label="run result")
        try:
            task_index = int(entry["task_index"])
        except (KeyError, TypeError, ValueError) as error:
            raise ArtifactError("run result has an invalid task index") from error
        if entry.get("status") != "complete" or task_index in task_indices:
            raise ArtifactError("run results must be uniquely complete")
        task_indices.add(task_index)
        method = str(entry.get("method"))
        if method not in methods:
            raise ArtifactError(f"run result contains undeclared method {method!r}")
        expected_checkpoint = checkpoint_expectations.get(method, ("", ""))
        if (
            str(entry.get("checkpoint_path", "")),
            str(entry.get("checkpoint_sha256", "")),
        ) != expected_checkpoint:
            raise ArtifactError(f"run result {method} checkpoint provenance disagrees")
    if task_indices != set(range(expected_episodes)):
        raise ArtifactError("run results do not cover the complete task index range")

    episode_file = _require_file(project_root, episode_manifest_path, label="episode manifest")
    results_file = _require_file(project_root, results_path, label="episode results")
    episode_frame = _read_parquet(episode_file, label="episode manifest")
    results_frame = _read_parquet(results_file, label="episode results")
    common_columns = {
        "task_index",
        "episode_id",
        "scenario_id",
        "replicate",
        "seed",
        "split",
        "method",
        "source_policy",
        "checkpoint_path",
        "checkpoint_sha256",
        "project_commit",
        "timeout_s",
    }
    _require_columns(
        episode_frame, common_columns | {"recovery_tau_on_override"}, label="episode manifest"
    )
    _require_columns(
        results_frame,
        common_columns | {"logical_episode_id", "outcome"},
        label="episode results",
    )
    if len(episode_frame) != expected_episodes or len(results_frame) != expected_episodes:
        raise ArtifactError("episode manifest/results row count disagrees with final configuration")
    for frame, label in (
        (episode_frame, "episode manifest"),
        (results_frame, "episode results"),
    ):
        if _single_string(frame, "split", label=label) != "test":
            raise ArtifactError(f"{label} is not exclusively test data")
        if _single_string(frame, "project_commit", label=label) != evaluation_commit:
            raise ArtifactError(f"{label} project_commit disagrees with run manifest")
        if set(frame["source_policy"].astype(str)) != set(methods):
            raise ArtifactError(f"{label} method set disagrees with final configuration")
        if not (frame["method"].astype(str) == frame["source_policy"].astype(str)).all():
            raise ArtifactError(f"{label} method/source_policy columns disagree")
        counts = frame.groupby("source_policy", dropna=False).size().to_dict()
        if counts != {method: expected_per_method for method in methods}:
            raise ArtifactError(f"{label} per-method counts disagree with final configuration")
        if not (pd.to_numeric(frame["timeout_s"]) == float(runtime["episode_timeout_s"])).all():
            raise ArtifactError(f"{label} timeout disagrees with final configuration")
        for method in methods:
            subset = frame.loc[frame["source_policy"].astype(str) == method]
            expected_path, expected_hash = checkpoint_expectations.get(method, ("", ""))
            paths = set(subset["checkpoint_path"].fillna("").astype(str))
            hashes = set(subset["checkpoint_sha256"].fillna("").astype(str))
            if paths != {expected_path} or hashes != {expected_hash}:
                raise ArtifactError(f"{label} {method} checkpoint provenance disagrees")
    if set(episode_frame["recovery_tau_on_override"].fillna("").astype(str)) != {""}:
        raise ArtifactError("episode manifest contains a held-out threshold override")

    episode_by_task = episode_frame.set_index("task_index", verify_integrity=True).sort_index()
    results_by_task = results_frame.set_index("task_index", verify_integrity=True).sort_index()
    if set(episode_by_task.index) != set(results_by_task.index):
        raise ArtifactError("episode manifest/results task indices disagree")
    # ``episode_manifest.episode_id`` is the immutable logical identifier (the
    # physical a0 attempt).  Collection keeps that value in
    # ``results.logical_episode_id`` while ``results.episode_id`` records the
    # physical attempt that produced the algorithm outcome (a0, a1, or a2).
    # Compare every other identity column directly and validate the two ID
    # relationships separately below.
    identity_columns = common_columns - {"task_index", "episode_id"}
    for column in sorted(identity_columns):
        left = episode_by_task[column].fillna("").astype(str).tolist()
        right = results_by_task[column].fillna("").astype(str).tolist()
        if left != right:
            raise ArtifactError(f"episode manifest/results disagree in {column}")
    logical_episode_ids = episode_by_task["episode_id"].fillna("").astype(str).tolist()
    collected_logical_ids = results_by_task["logical_episode_id"].fillna("").astype(str).tolist()
    if logical_episode_ids != collected_logical_ids:
        raise ArtifactError("episode manifest episode_id/results logical_episode_id disagree")
    run_by_task = {
        int(_mapping(entry, label="run result")["task_index"]): _mapping(entry, label="run result")
        for entry in run_results
    }
    for task_index, row in episode_by_task.iterrows():
        run_entry = run_by_task[int(task_index)]
        result_row = results_by_task.loc[task_index]
        expected_checkpoint = checkpoint_expectations.get(str(row["source_policy"]), ("", ""))
        if str(run_entry.get("episode_id", "")) != str(result_row["episode_id"]):
            raise ArtifactError("run manifest episode_id/results physical episode_id disagree")
        if (
            str(run_entry.get("scenario_id", "")) != str(row["scenario_id"])
            or str(run_entry.get("replicate", "")) != str(row["replicate"])
            or str(run_entry.get("method")) != str(row["source_policy"])
            or (
                str(run_entry.get("checkpoint_path", "")),
                str(run_entry.get("checkpoint_sha256", "")),
            )
            != expected_checkpoint
        ):
            raise ArtifactError("run results disagree with the episode manifest identity")
    invalid_outcomes = (
        set(results_frame["outcome"].astype(str))
        - ALGORITHM_OUTCOMES
        - {
            "SIMULATOR_FAILURE",
            "INVALID_RESET",
        }
    )
    if invalid_outcomes:
        raise ArtifactError(f"episode results contain invalid outcomes: {sorted(invalid_outcomes)}")

    return {
        "evaluation_commit": evaluation_commit,
        "evaluation_config_sha256": sha256_file(evaluation_config_file),
        "expected_conditions_per_method": expected_per_method,
        "expected_episodes": expected_episodes,
        "methods": methods,
        "run_id": run_id,
        "run_manifest_sha256": sha256_file(run_manifest_file),
        "episode_manifest_sha256": sha256_file(episode_file),
        "results_sha256": sha256_file(results_file),
        "split_manifest": _relative(project_root, test_split),
        "split_manifest_sha256": sha256_file(test_split),
        "method_checkpoints": {
            method: {"path": path, "sha256": digest}
            for method, (path, digest) in sorted(checkpoint_expectations.items())
        },
    }


def _validate_runtime_capture(
    project_root: Path,
    *,
    screenshot: Path,
    source_screenshot: Path,
    metadata_path: Path,
) -> None:
    metadata = _load_json_object(metadata_path, label="runtime screenshot metadata")
    if metadata.get("artifact_type") != "real_arena_gazebo_gui_screenshot":
        raise ArtifactError("runtime screenshot is not declared as a real Arena/Gazebo capture")
    if metadata.get("capture_target") != "Gazebo GUI window":
        raise ArtifactError("runtime screenshot capture target is not the Gazebo GUI window")
    backend = str(metadata.get("capture_backend", "")).lower()
    if not backend or "synthetic" in backend or "render" == backend:
        raise ArtifactError("runtime screenshot capture backend is missing or synthetic")
    _require_commit(metadata.get("git_commit"), label="runtime screenshot git_commit")
    _require_commit(metadata.get("arena_commit"), label="runtime screenshot arena_commit")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", str(metadata.get("arena_image_id"))) is None:
        raise ArtifactError("runtime screenshot arena_image_id is not a pinned digest")
    if metadata.get("episode_outcome") not in ALGORITHM_OUTCOMES:
        raise ArtifactError("runtime screenshot does not reference an algorithm episode outcome")

    launch = _mapping(metadata.get("launch_profile"), label="runtime launch_profile")
    if (
        launch.get("simulator") != "gazebo"
        or type(launch.get("headless")) is not int
        or launch.get("headless") != 0
        or launch.get("local_planner") != "dwb"
    ):
        raise ArtifactError("runtime screenshot launch profile is not Gazebo GUI + Nav2 DWB")
    camera = _mapping(metadata.get("camera_framing"), label="runtime camera_framing")
    if (
        camera.get("framing") != "scenario_midpoint_oblique"
        or camera.get("transport_service") != "/gui/move_to/pose"
    ):
        raise ArtifactError("runtime screenshot lacks the reproducible Gazebo camera pose")
    window = _mapping(metadata.get("window"), label="runtime window")
    if re.search(r"Gazebo|gz sim", str(window.get("title", "")), re.IGNORECASE) is None:
        raise ArtifactError("runtime screenshot metadata does not identify a Gazebo window")
    visual = _mapping(metadata.get("visual_validation"), label="runtime visual_validation")
    try:
        viewport_stddev = float(visual["scene_viewport_grayscale_stddev"])
        viewport_colors = int(visual["scene_viewport_unique_colors"])
    except (KeyError, TypeError, ValueError) as error:
        raise ArtifactError("runtime screenshot visual validation is incomplete") from error
    if viewport_stddev < 15.0 or viewport_colors < 300:
        raise ArtifactError("runtime screenshot Scene3D viewport is blank or incomplete")

    artifacts = _mapping(metadata.get("artifacts"), label="runtime capture artifacts")
    expected_paths = {
        "screenshot": _relative(project_root, source_screenshot),
        "paper_copy": _relative(project_root, screenshot),
    }
    for key, expected in expected_paths.items():
        declared = str(artifacts.get(key, ""))
        if declared != expected:
            raise ArtifactError(f"runtime capture {key} path disagrees with publication path")
    declared_hash = _require_sha256(
        artifacts.get("screenshot_sha256"), label="runtime screenshot hash"
    )
    if sha256_file(source_screenshot) != declared_hash or sha256_file(screenshot) != declared_hash:
        raise ArtifactError("runtime screenshot copies disagree with capture metadata")

    dimensions = _mapping(metadata.get("dimensions"), label="runtime dimensions")
    for image_path in (source_screenshot, screenshot):
        try:
            with Image.open(image_path) as image:
                image.load()
                if image.format != "PNG" or image.width < 640 or image.height < 480:
                    raise ArtifactError("runtime screenshot is not a publication-size PNG")
                if image.info:
                    raise ArtifactError("runtime screenshot contains ancillary PNG metadata")
                if (image.width, image.height) != (
                    int(dimensions.get("width_px", -1)),
                    int(dimensions.get("height_px", -1)),
                ):
                    raise ArtifactError("runtime screenshot dimensions disagree with metadata")
        except OSError as error:
            raise ArtifactError(f"cannot decode runtime screenshot: {image_path}") from error

    scenario = _mapping(metadata.get("scenario"), label="runtime scenario")
    scenario_path = _require_file(
        project_root, Path(str(scenario.get("path", ""))), label="runtime capture scenario"
    )
    scenario_payload = _load_json_object(scenario_path, label="runtime capture scenario")
    scenario_metadata = _mapping(
        scenario_payload.get("ramp_metadata"), label="runtime scenario ramp_metadata"
    )
    for key in ("scenario_id", "family", "density", "seed", "split"):
        if scenario.get(key) != scenario_metadata.get(key):
            raise ArtifactError(f"runtime capture scenario {key} disagrees with scenario file")
    if scenario.get("split") == "test":
        raise ArtifactError("runtime screenshot must not be selected from held-out test episodes")


def _git_commit(project_root: Path) -> str:
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(project_root), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.PIPE,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ArtifactError("cannot resolve the repository Git commit") from error
    if len(commit) != 40:
        raise ArtifactError(f"unexpected Git commit value: {commit!r}")
    return commit


def _git_is_dirty(project_root: Path) -> bool:
    try:
        status = subprocess.check_output(
            ["git", "-C", str(project_root), "status", "--porcelain"],
            text=True,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ArtifactError("cannot inspect the repository Git status") from error
    return bool(status.strip())


def _artifact_record(project_root: Path, category: str, path: Path) -> dict[str, Any]:
    return {
        "category": category,
        "path": path.relative_to(project_root).as_posix(),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _validate_existing_manifest(path: Path, current: Mapping[str, Any]) -> None:
    """Require the published manifest to match a fresh read-only reconstruction.

    Timestamps and the commit that assembled the archive are intentionally not
    compared: committing the generated bundle necessarily happens after the
    development build.  Every scientific provenance field and every artifact
    path, category, size, hash, and validated document/media property is
    compared exactly.
    """

    existing = _load_json_object(path, label="published artifact manifest")
    compared_keys = (
        "schema_version",
        "evaluation_commit",
        "evaluation_provenance",
        "document_pages",
        "video_metadata",
        "artifact_count",
        "category_counts",
        "artifacts",
    )
    mismatches = [key for key in compared_keys if existing.get(key) != current.get(key)]
    if mismatches:
        raise ArtifactError(
            "published artifact manifest is stale or tampered; mismatched fields: "
            + ", ".join(mismatches)
        )


def _pdf_page_count(path: Path, *, label: str) -> int:
    """Return a PDF page count using the release-declared Poppler tooling."""

    executable = shutil.which("pdfinfo")
    if executable is None:
        raise ArtifactError(f"pdfinfo is required to validate {label}")
    try:
        completed = subprocess.run(
            [executable, str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ArtifactError(f"cannot inspect {label}: {path}") from error
    match = re.search(r"^Pages:\s+(\d+)\s*$", completed.stdout, flags=re.MULTILINE)
    if match is None:
        raise ArtifactError(f"pdfinfo did not report a page count for {label}")
    return int(match.group(1))


def _require_pdf_pages(path: Path, *, expected: int, label: str) -> int:
    observed = _pdf_page_count(path, label=label)
    if observed != expected:
        raise ArtifactError(f"{label} must contain exactly {expected} pages; found {observed}")
    return observed


def _require_pdf_page_range(
    path: Path,
    *,
    minimum: int,
    maximum: int,
    label: str,
) -> int:
    observed = _pdf_page_count(path, label=label)
    if not minimum <= observed <= maximum:
        raise ArtifactError(f"{label} must contain {minimum}--{maximum} pages; found {observed}")
    return observed


def _validate_offline_ablation(
    *,
    project_root: Path,
    csv_path: Path,
    sidecar_path: Path,
    dataset_path: Path,
) -> None:
    """Bind the published offline ablation to its tracked validation dataset."""

    sidecar = _load_json_object(sidecar_path, label="offline-ablation sidecar")
    if sidecar.get("schema_version") != 1:
        raise ArtifactError("offline-ablation sidecar must use schema_version 1")
    expected_csv = _relative(project_root, csv_path)
    expected_dataset = _relative(project_root, dataset_path)
    if sidecar.get("output") != expected_csv:
        raise ArtifactError("offline-ablation sidecar names a different CSV")
    if sidecar.get("output_sha256") != sha256_file(csv_path):
        raise ArtifactError("offline-ablation CSV hash disagrees with its sidecar")
    if sidecar.get("dataset") != expected_dataset:
        raise ArtifactError("offline-ablation sidecar names a different dataset")
    dataset_hash = sha256_file(dataset_path)
    if sidecar.get("dataset_sha256") != dataset_hash:
        raise ArtifactError("offline-ablation dataset hash disagrees with its sidecar")
    try:
        frame = pd.read_csv(csv_path)
    except (OSError, pd.errors.ParserError) as error:
        raise ArtifactError(f"invalid offline-ablation CSV: {csv_path}") from error
    required = {"dataset", "dataset_sha256", "sample_count"}
    if missing := sorted(required - set(frame.columns)):
        raise ArtifactError("offline-ablation CSV is missing columns: " + ", ".join(missing))
    if set(frame["dataset"].astype(str)) != {expected_dataset}:
        raise ArtifactError("offline-ablation CSV names a different dataset")
    if set(frame["dataset_sha256"].astype(str)) != {dataset_hash}:
        raise ArtifactError("offline-ablation CSV dataset hash disagrees with the tracked file")
    sample_counts = pd.to_numeric(frame["sample_count"], errors="coerce")
    if sample_counts.isna().any() or set(sample_counts.astype(int)) != {
        int(sidecar.get("sample_count", -1))
    }:
        raise ArtifactError("offline-ablation sample count disagrees with its sidecar")


def _validate_png(path: Path, *, label: str, require_contrast: bool = False) -> None:
    """Decode a raster fully and optionally reject blank review sheets."""

    try:
        with Image.open(path) as image:
            if image.format != "PNG":
                raise ArtifactError(f"{label} must be a PNG image")
            image.load()
            if image.width <= 0 or image.height <= 0:
                raise ArtifactError(f"{label} has empty dimensions")
            if require_contrast:
                sample = image.convert("RGB")
                sample.thumbnail((512, 512))
                pixels = list(sample.get_flattened_data())
                luminance = [sum(pixel) / 3.0 for pixel in pixels]
                nonwhite_ratio = sum(value < 248.0 for value in luminance) / len(luminance)
                if max(luminance) - min(luminance) < 12.0 or nonwhite_ratio < 0.01:
                    raise ArtifactError(f"{label} is blank or has insufficient visual contrast")
    except ArtifactError:
        raise
    except (OSError, ValueError) as error:
        raise ArtifactError(f"invalid {label}: {path}") from error


def _validate_video(path: Path) -> dict[str, Any]:
    """Use ffprobe to require a readable, non-empty, positive-duration video stream."""

    executable = shutil.which("ffprobe")
    if executable is None:
        raise ArtifactError("ffprobe is required to validate the telemetry video")
    try:
        completed = subprocess.run(
            [
                executable,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-count_frames",
                "-show_entries",
                "stream=codec_name,codec_type,width,height,duration,nb_read_frames",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        raise ArtifactError(f"telemetry video cannot be decoded by ffprobe: {path}") from error
    streams = payload.get("streams")
    if not isinstance(streams, list) or len(streams) != 1:
        raise ArtifactError("telemetry MP4 must contain a readable video stream")
    stream = _mapping(streams[0], label="telemetry video stream")
    if stream.get("codec_type") != "video" or not str(stream.get("codec_name", "")):
        raise ArtifactError("telemetry MP4 does not declare a decodable video codec")
    try:
        width = int(stream.get("width", 0))
        height = int(stream.get("height", 0))
        frame_count = int(stream.get("nb_read_frames", 0))
        stream_duration = float(stream.get("duration", "nan"))
        format_payload = _mapping(payload.get("format", {}), label="telemetry video format")
        format_duration = float(format_payload.get("duration", "nan"))
    except (TypeError, ValueError) as error:
        raise ArtifactError("telemetry MP4 has invalid stream metadata") from error
    durations = [value for value in (stream_duration, format_duration) if value > 0.0]
    if width <= 0 or height <= 0 or frame_count <= 0 or not durations:
        raise ArtifactError("telemetry MP4 must have frames, dimensions, and positive duration")
    return {
        "codec": str(stream["codec_name"]),
        "width": width,
        "height": height,
        "frame_count": frame_count,
        "duration_s": max(durations),
    }


def _validate_report_data(
    path: Path,
    *,
    project_root: Path,
    results_path: Path,
    results_sha256: str,
    statistics_path: Path,
    statistics_sha256: str,
    expected_conditions: int,
    expected_episodes: int,
) -> None:
    """Bind the detailed report and deck to the same locked test result."""

    payload = _load_json_object(path, label="technical-report data")
    if payload.get("schema_version") != 2:
        raise ArtifactError("technical-report data must use schema_version 2")
    if payload.get("stage") != "test" or payload.get("results_available") is not True:
        raise ArtifactError("technical-report data must declare the locked test stage")
    if payload.get("author_alias") != "Charles Chen":
        raise ArtifactError("technical-report data must use the approved Charles Chen alias")
    expected_path = _relative(project_root, results_path)
    if payload.get("results_path") != expected_path:
        raise ArtifactError("technical-report data does not reference the locked final results")
    if payload.get("results_sha256") != results_sha256:
        raise ArtifactError("technical-report data hash disagrees with the locked final results")
    expected_statistics_path = _relative(project_root, statistics_path)
    if payload.get("statistics_path") != expected_statistics_path:
        raise ArtifactError(
            "technical-report data does not reference the locked pairwise statistics"
        )
    if payload.get("statistics_sha256") != statistics_sha256:
        raise ArtifactError(
            "technical-report data hash disagrees with the locked pairwise statistics"
        )
    try:
        condition_count = int(payload["condition_count"])
        episode_count = int(payload["episode_count"])
        valid_count = int(payload["valid_episode_count"])
        excluded_count = int(payload["excluded_episode_count"])
    except (KeyError, TypeError, ValueError) as error:
        raise ArtifactError("technical-report data has invalid result counts") from error
    if condition_count != expected_conditions or episode_count != expected_episodes:
        raise ArtifactError("technical-report data counts disagree with the frozen test protocol")
    if valid_count < 0 or excluded_count < 0 or valid_count + excluded_count != episode_count:
        raise ArtifactError("technical-report valid/excluded counts do not cover every episode")
    paired = payload.get("paired_comparisons")
    if not isinstance(paired, list) or len(paired) != 12:
        raise ArtifactError("technical-report data must contain all 12 paired comparisons")
    observed_pairs = {
        (str(record.get("comparator")), str(record.get("endpoint")))
        for record in paired
        if isinstance(record, Mapping)
    }
    expected_pairs = {
        (comparator, endpoint)
        for comparator in ("base", "standard", "heuristic", "bc_uniform")
        for endpoint in ("goal_reached", "collision", "timeout")
    }
    if observed_pairs != expected_pairs:
        raise ArtifactError("technical-report paired comparison matrix is incomplete")


def _validate_presentation(pptx: Path, notes: Path, contact_sheet: Path) -> None:
    """Require a structurally complete 30-slide briefing and its review aids."""

    try:
        with zipfile.ZipFile(pptx) as archive:
            slide_names = {
                name
                for name in archive.namelist()
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
            }
            try:
                core_properties = ET.fromstring(archive.read("docProps/core.xml"))
            except KeyError as error:
                raise ArtifactError("presentation PPTX is missing core properties") from error
            except ET.ParseError as error:
                raise ArtifactError("presentation PPTX has invalid core properties") from error
    except (OSError, zipfile.BadZipFile) as error:
        raise ArtifactError(f"invalid presentation PPTX: {pptx}") from error
    expected_slide_names = {f"ppt/slides/slide{number}.xml" for number in range(1, 31)}
    if slide_names != expected_slide_names:
        raise ArtifactError(
            f"presentation PPTX must contain exactly 30 slides; found {len(slide_names)}"
        )
    namespaces = {
        "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
        "dc": "http://purl.org/dc/elements/1.1/",
    }
    creator = core_properties.findtext("dc:creator", default="", namespaces=namespaces)
    modified_by = core_properties.findtext("cp:lastModifiedBy", default="", namespaces=namespaces)
    subject = core_properties.findtext("dc:subject", default="", namespaces=namespaces)
    if subject.split(";", maxsplit=1)[0].strip() != "stage=test":
        raise ArtifactError("presentation PPTX is not bound to the locked test stage")
    if creator != "Charles Chen" or modified_by != "Charles Chen":
        raise ArtifactError(
            "presentation PPTX creator and lastModifiedBy must use the approved alias"
        )

    notes_text = notes.read_text(encoding="utf-8")
    note_sections = re.findall(r"^##\s+(\d{2})\.\s+", notes_text, flags=re.MULTILINE)
    expected_note_sections = [f"{number:02d}" for number in range(1, 31)]
    if note_sections != expected_note_sections:
        raise ArtifactError(
            f"presentation speaker notes must contain 30 slide sections; found {len(note_sections)}"
        )
    if "阶段\uff1a`test`" not in notes_text:
        raise ArtifactError("presentation speaker notes are not bound to the locked test stage")
    _validate_png(contact_sheet, label="presentation contact sheet", require_contrast=True)
    with Image.open(contact_sheet) as image:
        width, height = image.size
    if width < 1000 or height < 500:
        raise ArtifactError("presentation contact sheet is too small for visual review")


def build_manifest(
    project_root: Path,
    *,
    config_path: Path = DEFAULT_CONFIG,
    evaluation_config_path: Path = DEFAULT_EVALUATION_CONFIG,
    baseline_config_path: Path = DEFAULT_BASELINE_CONFIG,
    uniform_checkpoint_path: Path = DEFAULT_UNIFORM_CHECKPOINT,
    checkpoint_path: Path = DEFAULT_CHECKPOINT,
    results_path: Path = DEFAULT_RESULTS,
    summary_path: Path = DEFAULT_SUMMARY,
    statistics_path: Path = DEFAULT_STATISTICS,
    calibration_report_path: Path = DEFAULT_CALIBRATION_REPORT,
    test_split_path: Path = DEFAULT_TEST_SPLIT,
    failure_analysis_path: Path = DEFAULT_FAILURE_ANALYSIS,
    episode_manifest_path: Path = DEFAULT_EPISODE_MANIFEST,
    run_manifest_path: Path = DEFAULT_RUN_MANIFEST,
    offline_ablation_path: Path = DEFAULT_OFFLINE_ABLATION_CSV,
    offline_ablation_dataset_path: Path = DEFAULT_OFFLINE_ABLATION_DATASET,
    figures_dir: Path = DEFAULT_FIGURES_DIR,
    tables_dir: Path = DEFAULT_TABLES_DIR,
    media_keyframes_pdf_path: Path = DEFAULT_MEDIA_KEYFRAMES_PDF,
    media_keyframes_png_path: Path = DEFAULT_MEDIA_KEYFRAMES_PNG,
    video_path: Path = DEFAULT_VIDEO,
    paper_path: Path = DEFAULT_PAPER,
    report_path: Path = DEFAULT_REPORT,
    report_data_path: Path = DEFAULT_REPORT_DATA,
    presentation_pptx_path: Path = DEFAULT_PRESENTATION_PPTX,
    presentation_pdf_path: Path = DEFAULT_PRESENTATION_PDF,
    presentation_notes_path: Path = DEFAULT_PRESENTATION_NOTES,
    presentation_contact_sheet_path: Path = DEFAULT_PRESENTATION_CONTACT_SHEET,
    generation_command: str = "scripts/reproduce_paper.sh",
    generated_at: str | None = None,
    project_commit: str | None = None,
    git_dirty: bool | None = None,
    release: bool = False,
) -> dict[str, Any]:
    """Validate and describe the complete paper artifact set."""

    root = project_root.resolve()
    artifact_generation_commit = (
        _require_commit(project_commit, label="artifact generation commit")
        if project_commit is not None
        else _git_commit(root)
    )
    dirty = git_dirty if git_dirty is not None else _git_is_dirty(root)
    if release and dirty:
        raise ArtifactError("release artifact generation requires a clean Git worktree")

    provenance = _validate_evaluation_provenance(
        root,
        config_path=config_path,
        evaluation_config_path=evaluation_config_path,
        baseline_config_path=baseline_config_path,
        uniform_checkpoint_path=uniform_checkpoint_path,
        checkpoint_path=checkpoint_path,
        results_path=results_path,
        calibration_report_path=calibration_report_path,
        test_split_path=test_split_path,
        episode_manifest_path=episode_manifest_path,
        run_manifest_path=run_manifest_path,
    )
    singleton_specs = (
        ("final_config", config_path, "final configuration"),
        ("final_config", evaluation_config_path, "final evaluation configuration"),
        ("final_config", baseline_config_path, "baseline configuration"),
        ("checkpoint", uniform_checkpoint_path, "Uniform BC checkpoint"),
        ("checkpoint", checkpoint_path, "selected checkpoint"),
        ("episode_manifest", episode_manifest_path, "episode manifest"),
        ("run_manifest", run_manifest_path, "run manifest"),
        ("results", results_path, "episode results"),
        ("summary", summary_path, "result summary"),
        ("statistics", statistics_path, "statistics report"),
        (
            "calibration_report",
            calibration_report_path,
            "moderate calibration report",
        ),
        ("failure_analysis", failure_analysis_path, "failure analysis"),
        (
            "offline_ablation",
            offline_ablation_path,
            "offline ablation CSV",
        ),
        (
            "offline_ablation",
            offline_ablation_path.with_suffix(".json"),
            "offline ablation provenance",
        ),
        (
            "offline_ablation_dataset",
            offline_ablation_dataset_path,
            "offline ablation dataset",
        ),
        ("paper_source", DEFAULT_MAIN_TEX, "paper TeX source"),
        ("paper_source", DEFAULT_REFERENCES, "paper references"),
        ("claim_evidence", DEFAULT_CLAIM_MATRIX, "claim-evidence matrix"),
        ("environment_lock", DEFAULT_ENVIRONMENT_LOCK, "Conda environment lock"),
        ("environment_lock", DEFAULT_REQUIREMENTS_LOCK, "pip environment lock"),
        ("runtime_lock", DEFAULT_ARENA_LOCK, "Arena commit lock"),
        (
            "runtime_lock",
            DEFAULT_DEPENDENCY_MANIFEST,
            "runtime dependency manifest",
        ),
        ("frozen_input", test_split_path, "test split"),
        ("frozen_input", DEFAULT_FAILURE_CONFIG, "failure-detector configuration"),
        (
            "frozen_input",
            DEFAULT_STATE_MACHINE_CONFIG,
            "recovery-state-machine configuration",
        ),
        ("frozen_input", DEFAULT_ACTION_CONFIG, "recovery-action configuration"),
        ("paper", paper_path, "paper PDF"),
        ("technical_report", report_path, "technical-report PDF"),
        ("report_data", report_data_path, "technical-report data"),
        ("presentation", presentation_pptx_path, "presentation PPTX"),
        ("presentation", presentation_pdf_path, "presentation PDF"),
        ("presentation_notes", presentation_notes_path, "presentation speaker notes"),
        (
            "presentation_contact_sheet",
            presentation_contact_sheet_path,
            "presentation contact sheet",
        ),
    )
    artifacts: list[tuple[str, Path]] = []
    for category, path, label in singleton_specs:
        artifacts.append((category, _require_file(root, path, label=label)))
    resolved_calibration_report = _require_file(
        root,
        calibration_report_path,
        label="moderate calibration report",
    )
    _validate_calibration_report(resolved_calibration_report)

    resolved_ablation = _require_file(root, offline_ablation_path, label="offline ablation CSV")
    resolved_ablation_sidecar = _require_file(
        root,
        offline_ablation_path.with_suffix(".json"),
        label="offline ablation provenance",
    )
    resolved_ablation_dataset = _require_file(
        root,
        offline_ablation_dataset_path,
        label="offline ablation dataset",
    )
    _validate_offline_ablation(
        project_root=root,
        csv_path=resolved_ablation,
        sidecar_path=resolved_ablation_sidecar,
        dataset_path=resolved_ablation_dataset,
    )

    resolved_results = _require_file(root, results_path, label="episode results")
    resolved_statistics = _require_file(root, statistics_path, label="statistics report")
    resolved_paper = _require_file(root, paper_path, label="paper PDF")
    resolved_report = _require_file(root, report_path, label="technical-report PDF")
    resolved_report_data = _require_file(root, report_data_path, label="technical-report data")
    resolved_presentation_pptx = _require_file(
        root, presentation_pptx_path, label="presentation PPTX"
    )
    resolved_presentation_pdf = _require_file(root, presentation_pdf_path, label="presentation PDF")
    resolved_presentation_notes = _require_file(
        root, presentation_notes_path, label="presentation speaker notes"
    )
    resolved_contact_sheet = _require_file(
        root,
        presentation_contact_sheet_path,
        label="presentation contact sheet",
    )
    _validate_report_data(
        resolved_report_data,
        project_root=root,
        results_path=resolved_results,
        results_sha256=provenance["results_sha256"],
        statistics_path=resolved_statistics,
        statistics_sha256=sha256_file(resolved_statistics),
        expected_conditions=int(provenance["expected_conditions_per_method"]),
        expected_episodes=int(provenance["expected_episodes"]),
    )
    paper_pages = _require_pdf_pages(resolved_paper, expected=8, label="conference paper")
    report_pages = _require_pdf_page_range(
        resolved_report,
        minimum=30,
        maximum=40,
        label="technical report",
    )
    presentation_pages = _require_pdf_pages(
        resolved_presentation_pdf, expected=30, label="presentation PDF"
    )
    _validate_presentation(
        resolved_presentation_pptx,
        resolved_presentation_notes,
        resolved_contact_sheet,
    )

    resolved_figures_dir = _inside_root(root, figures_dir, label="figures directory")
    for filename in EXPECTED_FIGURES:
        artifacts.append(
            (
                "figure",
                _require_file(
                    root,
                    resolved_figures_dir / filename,
                    label=f"generated figure {filename}",
                ),
            )
        )

    resolved_tables_dir = _inside_root(root, tables_dir, label="tables directory")
    for filename in EXPECTED_TABLES:
        artifacts.append(
            (
                "table",
                _require_file(
                    root,
                    resolved_tables_dir / filename,
                    label=f"generated table {filename}",
                ),
            )
        )

    for source in sorted((root / "paper" / "sections").glob("*.tex")):
        artifacts.append(("paper_source", _require_file(root, source, label="paper section")))
    if not any(
        category == "paper_source" and path.parent.name == "sections"
        for category, path in artifacts
    ):
        raise ArtifactError("missing required paper sections: paper/sections/*.tex")

    resolved_output_figures = _inside_root(
        root, DEFAULT_OUTPUT_FIGURES_DIR, label="published figures directory"
    )
    for filename in EXPECTED_FIGURES:
        artifacts.append(
            (
                "published_figure",
                _require_file(
                    root,
                    resolved_output_figures / filename,
                    label=f"published figure {filename}",
                ),
            )
        )

    resolved_output_tables = _inside_root(
        root, DEFAULT_OUTPUT_TABLES_DIR, label="published tables directory"
    )
    for filename in EXPECTED_TABLES:
        artifacts.append(
            (
                "published_table",
                _require_file(
                    root,
                    resolved_output_tables / filename,
                    label=f"published table {filename}",
                ),
            )
        )

    resolved_video = _require_file(root, video_path, label="final telemetry video")
    artifacts.append(("video", resolved_video))
    resolved_keyframes_pdf = _require_file(
        root,
        media_keyframes_pdf_path,
        label="final telemetry keyframes PDF",
    )
    artifacts.append(
        (
            "runtime_keyframe",
            resolved_keyframes_pdf,
        )
    )
    resolved_keyframes_png = _require_file(
        root,
        media_keyframes_png_path,
        label="final telemetry keyframes PNG",
    )
    artifacts.append(
        (
            "runtime_keyframe",
            resolved_keyframes_png,
        )
    )
    keyframe_pages = _require_pdf_pages(
        resolved_keyframes_pdf,
        expected=1,
        label="telemetry keyframes PDF",
    )
    _validate_png(resolved_keyframes_png, label="telemetry keyframes PNG")
    video_metadata = _validate_video(resolved_video)

    runtime_screenshot = _inside_root(
        root,
        OPTIONAL_RUNTIME_SCREENSHOT,
        label="optional runtime screenshot",
    )
    runtime_metadata = _inside_root(
        root,
        OPTIONAL_RUNTIME_CAPTURE_METADATA,
        label="optional runtime screenshot metadata",
    )
    runtime_source = _inside_root(
        root,
        OPTIONAL_RUNTIME_SCREENSHOT_SOURCE,
        label="optional runtime screenshot source",
    )
    capture_presence = {
        runtime_screenshot.exists(),
        runtime_source.exists(),
        runtime_metadata.exists(),
    }
    if len(capture_presence) != 1:
        raise ArtifactError(
            "runtime screenshot copies and capture metadata must all exist or all be absent"
        )
    if release and not runtime_screenshot.exists():
        raise ArtifactError("release artifacts require a verified real Gazebo runtime screenshot")
    if runtime_screenshot.exists():
        runtime_screenshot = _require_file(root, runtime_screenshot, label="runtime screenshot")
        runtime_source = _require_file(root, runtime_source, label="runtime screenshot source")
        runtime_metadata = _require_file(
            root, runtime_metadata, label="runtime screenshot metadata"
        )
        _validate_runtime_capture(
            root,
            screenshot=runtime_screenshot,
            source_screenshot=runtime_source,
            metadata_path=runtime_metadata,
        )
        artifacts.append(
            (
                "runtime_screenshot",
                runtime_screenshot,
            )
        )
        artifacts.append(("runtime_screenshot_source", runtime_source))
        artifacts.append(
            (
                "runtime_capture_metadata",
                runtime_metadata,
            )
        )

    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    records = [_artifact_record(root, category, path) for category, path in artifacts]
    counts = Counter(str(record["category"]) for record in records)
    return {
        "schema_version": 2,
        "generated_at": timestamp,
        "generation_command": generation_command,
        "evaluation_commit": provenance["evaluation_commit"],
        "artifact_generation_commit": artifact_generation_commit,
        "git_worktree_dirty": dirty,
        "release": release,
        "evaluation_provenance": provenance,
        "document_pages": {
            _relative(root, resolved_paper): paper_pages,
            _relative(root, resolved_report): report_pages,
            _relative(root, resolved_presentation_pdf): presentation_pages,
            _relative(root, resolved_keyframes_pdf): keyframe_pages,
        },
        "video_metadata": video_metadata,
        "artifact_count": len(records),
        "category_counts": dict(sorted(counts.items())),
        "artifacts": records,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--evaluation-config",
        type=Path,
        default=DEFAULT_EVALUATION_CONFIG,
    )
    parser.add_argument("--baseline-config", type=Path, default=DEFAULT_BASELINE_CONFIG)
    parser.add_argument("--uniform-checkpoint", type=Path, default=DEFAULT_UNIFORM_CHECKPOINT)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--statistics", type=Path, default=DEFAULT_STATISTICS)
    parser.add_argument("--calibration-report", type=Path, default=DEFAULT_CALIBRATION_REPORT)
    parser.add_argument("--test-split", type=Path, default=DEFAULT_TEST_SPLIT)
    parser.add_argument("--failure-analysis", type=Path, default=DEFAULT_FAILURE_ANALYSIS)
    parser.add_argument("--episode-manifest", type=Path, default=DEFAULT_EPISODE_MANIFEST)
    parser.add_argument("--run-manifest", type=Path, default=DEFAULT_RUN_MANIFEST)
    parser.add_argument(
        "--offline-ablation",
        type=Path,
        default=DEFAULT_OFFLINE_ABLATION_CSV,
    )
    parser.add_argument(
        "--offline-ablation-dataset",
        type=Path,
        default=DEFAULT_OFFLINE_ABLATION_DATASET,
    )
    parser.add_argument("--figures-dir", type=Path, default=DEFAULT_FIGURES_DIR)
    parser.add_argument("--tables-dir", type=Path, default=DEFAULT_TABLES_DIR)
    parser.add_argument("--media-keyframes-pdf", type=Path, default=DEFAULT_MEDIA_KEYFRAMES_PDF)
    parser.add_argument("--media-keyframes-png", type=Path, default=DEFAULT_MEDIA_KEYFRAMES_PNG)
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--paper", type=Path, default=DEFAULT_PAPER)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--report-data", type=Path, default=DEFAULT_REPORT_DATA)
    parser.add_argument("--presentation-pptx", type=Path, default=DEFAULT_PRESENTATION_PPTX)
    parser.add_argument("--presentation-pdf", type=Path, default=DEFAULT_PRESENTATION_PDF)
    parser.add_argument("--presentation-notes", type=Path, default=DEFAULT_PRESENTATION_NOTES)
    parser.add_argument(
        "--presentation-contact-sheet",
        type=Path,
        default=DEFAULT_PRESENTATION_CONTACT_SHEET,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--command", default="scripts/reproduce_paper.sh")
    parser.add_argument(
        "--release",
        action="store_true",
        help="fail unless the worktree is clean and the real runtime capture is verified",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate the declared bundle without writing or replacing the manifest",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = build_manifest(
            ROOT,
            config_path=args.config,
            evaluation_config_path=args.evaluation_config,
            baseline_config_path=args.baseline_config,
            uniform_checkpoint_path=args.uniform_checkpoint,
            checkpoint_path=args.checkpoint,
            results_path=args.results,
            summary_path=args.summary,
            statistics_path=args.statistics,
            calibration_report_path=args.calibration_report,
            test_split_path=args.test_split,
            failure_analysis_path=args.failure_analysis,
            episode_manifest_path=args.episode_manifest,
            run_manifest_path=args.run_manifest,
            offline_ablation_path=args.offline_ablation,
            offline_ablation_dataset_path=args.offline_ablation_dataset,
            figures_dir=args.figures_dir,
            tables_dir=args.tables_dir,
            media_keyframes_pdf_path=args.media_keyframes_pdf,
            media_keyframes_png_path=args.media_keyframes_png,
            video_path=args.video,
            paper_path=args.paper,
            report_path=args.report,
            report_data_path=args.report_data,
            presentation_pptx_path=args.presentation_pptx,
            presentation_pdf_path=args.presentation_pdf,
            presentation_notes_path=args.presentation_notes,
            presentation_contact_sheet_path=args.presentation_contact_sheet,
            generation_command=args.command,
            release=args.release,
        )
        output = _inside_root(ROOT.resolve(), args.output, label="artifact manifest output")
        if args.validate_only:
            published = _require_file(
                ROOT.resolve(),
                output,
                label="published artifact manifest",
            )
            _validate_existing_manifest(published, payload)
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_suffix(output.suffix + ".tmp")
            temporary.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(output)
    except (ArtifactError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    action = "validation" if args.validate_only else "write"
    print(
        f"Artifact manifest {action} PASS: {output.relative_to(ROOT)} "
        f"({payload['artifact_count']} files)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
