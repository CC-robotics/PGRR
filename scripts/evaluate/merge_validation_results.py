#!/usr/bin/env python3
"""Merge two complete, same-commit moderate-v6 validation result tables.

The command accepts one Base-only collected table and one four-method collected
table.  It validates all 360 logical rows and their source run manifests before
atomically writing a combined Parquet plus a separate merge manifest.  It never
constructs a synthetic simulator run manifest and exposes no test-split mode or
condition-selection options.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EVALUATE_DIR = Path(__file__).resolve().parent
for import_root in (ROOT, EVALUATE_DIR):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

import summarize_moderate as moderate_summary  # noqa: E402
from run_experiment import sha256_file  # noqa: E402

from scripts.paper import moderate_artifacts  # noqa: E402

METHODS = tuple(moderate_artifacts.METHODS)
METHOD_SET = frozenset(METHODS)
BASE_METHODS = frozenset(("base",))
OTHER_METHODS = METHOD_SET - BASE_METHODS
EXPECTED_CONDITIONS = 72
EXPECTED_ROWS = EXPECTED_CONDITIONS * len(METHODS)
RUN_ID_PATTERN = re.compile(r"[0-9a-f]{12}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")

# All collector fields below describe the physical condition or runtime shared
# across methods.  The publication utility contributes its established
# invariant schema; the validation runner contributes the final three fields.
REQUIRED_SHARED_COLUMNS = (
    "scenario_id",
    "seed",
    "map",
    "map_id",
    "family",
    "density",
    "replicate",
    "timeout_s",
    "recovery_tau_on_override",
    "planner_id",
    "arena_commit",
    "scenario",
    "scenario_path",
    "scenario_sha256",
    "robot_start",
    "robot_goal",
    "pedestrian_config_hash",
)
PAIR_SHARED_COLUMNS = tuple(
    dict.fromkeys((*moderate_artifacts.PAIR_INVARIANT_COLUMNS, *REQUIRED_SHARED_COLUMNS))
)


class MergeValidationError(RuntimeError):
    """Raised when a source result table or source run is not merge-compatible."""


@dataclass(frozen=True)
class InputBundle:
    """One collected result table and the real run manifest that produced it."""

    results_path: Path
    run_manifest_path: Path
    frame: pd.DataFrame
    run_manifest: dict[str, Any]
    methods: frozenset[str]
    results_sha256: str
    run_manifest_sha256: str
    run_id: str


@dataclass(frozen=True)
class AttemptManifestEvidence:
    """One preserved pre-resume run snapshot; never an algorithm result table."""

    path: Path
    sha256: str
    run_id: str
    status_counts: dict[str, int]
    expected_task_count: int
    completed_task_count: int
    no_outcome_error_count: int
    other_error_count: int
    worker_error_count: int
    requested_jobs: int
    effective_jobs: int
    no_outcome_keys: tuple[str, ...]


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MergeValidationError(f"cannot read {label}: {path}") from error
    if not isinstance(payload, dict):
        raise MergeValidationError(f"{label} must contain a JSON object: {path}")
    return payload


def _display_path(path: Path, project_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _one_string(frame: pd.DataFrame, column: str, *, label: str) -> str:
    if frame[column].isna().any():
        raise MergeValidationError(f"{label} contains a null {column}")
    values = {str(value) for value in frame[column].dropna().unique()}
    if len(values) != 1:
        raise MergeValidationError(f"{label} must contain exactly one {column}: {sorted(values)!r}")
    value = next(iter(values))
    if not value:
        raise MergeValidationError(f"{label} contains an empty {column}")
    return value


def _validate_frame(path: Path) -> tuple[pd.DataFrame, frozenset[str], str]:
    try:
        frame = pd.read_parquet(path)
    except (OSError, ValueError) as error:
        raise MergeValidationError(f"cannot read collected results: {path}") from error
    try:
        moderate_summary._required_columns(frame)
    except ValueError as error:
        raise MergeValidationError(str(error)) from error
    missing = sorted(
        {
            "task_index",
            "pair_id",
            "project_commit",
            "included_in_algorithm_metrics",
            *REQUIRED_SHARED_COLUMNS,
        }
        - set(frame.columns)
    )
    if missing:
        raise MergeValidationError(f"results are missing merge-contract columns: {missing}")
    if frame["pair_id"].isna().any() or frame["pair_id"].astype(str).str.strip().eq("").any():
        raise MergeValidationError("results require non-null, non-empty pair_id values")
    if frame["episode_id"].isna().any() or frame["episode_id"].astype(str).duplicated().any():
        raise MergeValidationError(
            "episode_id values must be non-null and unique within each input"
        )
    splits = set(frame["split"].astype(str))
    if splits != {"validation"}:
        raise MergeValidationError(
            f"merge inputs must contain validation rows only; observed splits={sorted(splits)!r}"
        )
    methods = frozenset(frame["source_policy"].astype(str))
    if not methods or not methods <= METHOD_SET:
        raise MergeValidationError(f"input contains unsupported methods: {sorted(methods)!r}")
    duplicate = frame.duplicated(subset=["source_policy", "pair_id"], keep=False)
    if bool(duplicate.any()):
        example = frame.loc[duplicate, ["source_policy", "pair_id"]].iloc[0].to_dict()
        raise MergeValidationError(f"duplicate method/pair row: {example!r}")
    counts = frame.groupby("source_policy", observed=True).size().to_dict()
    if any(int(count) != EXPECTED_CONDITIONS for count in counts.values()):
        raise MergeValidationError(
            f"every input method requires {EXPECTED_CONDITIONS} conditions; counts={counts!r}"
        )
    try:
        valid = moderate_artifacts.valid_mask(frame)
    except moderate_artifacts.ModerateArtifactError as error:
        raise MergeValidationError(str(error)) from error
    if not bool(valid.all()):
        raise MergeValidationError("every logical validation row requires an algorithm outcome")
    commit = _one_string(frame, "project_commit", label=str(path))
    if moderate_artifacts.PROJECT_COMMIT_PATTERN.fullmatch(commit) is None:
        raise MergeValidationError(f"project_commit must be one lowercase 40-hex value: {commit!r}")
    for column in ("scenario_sha256", "pedestrian_config_hash"):
        values = frame[column].astype(str)
        if not bool(values.map(lambda value: SHA256_PATTERN.fullmatch(value) is not None).all()):
            raise MergeValidationError(f"{column} must contain lowercase SHA256 values")
    arena_commits = frame["arena_commit"].astype(str)
    if not bool(
        arena_commits.map(
            lambda value: moderate_artifacts.PROJECT_COMMIT_PATTERN.fullmatch(value) is not None
        ).all()
    ):
        raise MergeValidationError("arena_commit must contain lowercase 40-hex values")
    if "method" in frame and not bool(
        frame["method"].astype(str).eq(frame["source_policy"].astype(str)).all()
    ):
        raise MergeValidationError("method disagrees with source_policy")
    return frame, methods, commit


def _validate_run_manifest(
    *,
    path: Path,
    frame: pd.DataFrame,
    methods: frozenset[str],
    commit: str,
) -> tuple[dict[str, Any], str]:
    payload = _load_json_object(path, label="source run manifest")
    if payload.get("schema_version") != 1:
        raise MergeValidationError("source run manifest must use schema_version 1")
    run_id = str(payload.get("run_id", ""))
    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise MergeValidationError(f"source run_id must be lowercase 12-hex: {run_id!r}")
    if payload.get("split") != "validation":
        raise MergeValidationError("source run manifest must declare split: validation")
    if payload.get("project_commit") != commit:
        raise MergeValidationError("source run project_commit disagrees with collected results")
    declared_methods = payload.get("methods")
    high_density_methods = payload.get("high_density_methods")
    if not isinstance(declared_methods, list) or not isinstance(high_density_methods, list):
        raise MergeValidationError("source run manifest has invalid method lists")
    if frozenset(str(value) for value in (*declared_methods, *high_density_methods)) != methods:
        raise MergeValidationError("source run method set disagrees with collected results")
    row_count = len(frame)
    if (
        payload.get("expected_task_count") != row_count
        or payload.get("completed_task_count") != row_count
    ):
        raise MergeValidationError("source run task counts disagree with collected result rows")
    if payload.get("worker_errors") != []:
        raise MergeValidationError("source run manifest contains worker errors")
    try:
        requested_jobs = int(payload["requested_jobs"])
        effective_jobs = int(payload["effective_jobs"])
    except (KeyError, TypeError, ValueError) as error:
        raise MergeValidationError("source run manifest has invalid job counts") from error
    if requested_jobs <= 0 or effective_jobs <= 0:
        raise MergeValidationError("source run manifest job counts must be positive")
    records = payload.get("results")
    if not isinstance(records, list) or len(records) != row_count:
        raise MergeValidationError("source run results list is incomplete")
    if any(
        not isinstance(record, Mapping) or record.get("status") != "complete" for record in records
    ):
        raise MergeValidationError("source run contains an incomplete logical task")
    task_indices = [int(record.get("task_index", -1)) for record in records]
    if len(task_indices) != len(set(task_indices)):
        raise MergeValidationError("source run reuses a task_index")
    frame_task_indices = {int(value) for value in frame["task_index"]}
    if set(task_indices) != frame_task_indices:
        raise MergeValidationError("source run task_index set disagrees with collected results")
    physical_ids = [str(record.get("episode_id", "")) for record in records]
    if any(not episode_id for episode_id in physical_ids) or len(physical_ids) != len(
        set(physical_ids)
    ):
        raise MergeValidationError("source run episode_id values must be non-empty and unique")
    if set(physical_ids) != set(frame["episode_id"].astype(str)):
        raise MergeValidationError("source run episode_id set disagrees with collected results")
    indexed_frame = frame.set_index("episode_id", drop=False)
    for record in records:
        episode_id = str(record["episode_id"])
        row = indexed_frame.loc[episode_id]
        if (
            str(record.get("method", "")) != str(row["source_policy"])
            or str(record.get("scenario_id", "")) != str(row["scenario_id"])
            or int(record.get("replicate", -1)) != int(row["replicate"])
            or int(record.get("task_index", -1)) != int(row["task_index"])
        ):
            raise MergeValidationError(
                f"source run logical-task metadata disagrees for episode {episode_id}"
            )
        attempts = record.get("attempts")
        if not isinstance(attempts, list) or not attempts:
            raise MergeValidationError(f"source run has no physical attempts for {episode_id}")
        final_attempt = attempts[-1]
        if not isinstance(final_attempt, Mapping) or (
            str(final_attempt.get("episode_id", "")) != episode_id
            or str(final_attempt.get("outcome", "")) != str(row["outcome"])
        ):
            raise MergeValidationError(
                f"source run final attempt disagrees with collected outcome for {episode_id}"
            )
    if not isinstance(payload.get("split_manifest"), str) or not SHA256_PATTERN.fullmatch(
        str(payload.get("split_manifest_sha256", ""))
    ):
        raise MergeValidationError("source run has invalid split-manifest provenance")
    if not isinstance(payload.get("episode_manifest"), str):
        raise MergeValidationError("source run has invalid episode-manifest provenance")
    try:
        timeout_s = float(payload["timeout_s"])
    except (KeyError, TypeError, ValueError) as error:
        raise MergeValidationError("source run has invalid timeout_s") from error
    if not bool(pd.to_numeric(frame["timeout_s"], errors="coerce").eq(timeout_s).all()):
        raise MergeValidationError("source run timeout_s disagrees with collected results")
    tau = str(payload.get("recovery_tau_on_override", ""))
    if not bool(frame["recovery_tau_on_override"].astype(str).eq(tau).all()):
        raise MergeValidationError(
            "source run recovery_tau_on_override disagrees with collected results"
        )
    return payload, run_id


def load_input_bundle(results_path: Path, run_manifest_path: Path) -> InputBundle:
    """Load and cross-check one collected table with its real source run."""

    resolved_results = results_path.resolve()
    resolved_run = run_manifest_path.resolve()
    if not resolved_results.is_file():
        raise MergeValidationError(f"missing collected results: {resolved_results}")
    if not resolved_run.is_file():
        raise MergeValidationError(f"missing source run manifest: {resolved_run}")
    frame, methods, commit = _validate_frame(resolved_results)
    run_manifest, run_id = _validate_run_manifest(
        path=resolved_run,
        frame=frame,
        methods=methods,
        commit=commit,
    )
    return InputBundle(
        results_path=resolved_results,
        run_manifest_path=resolved_run,
        frame=frame,
        run_manifest=run_manifest,
        methods=methods,
        results_sha256=sha256_file(resolved_results),
        run_manifest_sha256=sha256_file(resolved_run),
        run_id=run_id,
    )


def load_attempt_manifest(
    path: Path,
    bundles: Sequence[InputBundle],
) -> AttemptManifestEvidence:
    """Validate one historical run snapshot without promoting errors to outcomes."""

    resolved = path.resolve()
    if not resolved.is_file():
        raise MergeValidationError(f"missing source attempt manifest: {resolved}")
    if resolved in {bundle.run_manifest_path.resolve() for bundle in bundles}:
        raise MergeValidationError(
            "source attempt manifest must be distinct from the final completeness manifest"
        )
    payload = _load_json_object(resolved, label="source attempt manifest")
    if payload.get("schema_version") != 1 or payload.get("split") != "validation":
        raise MergeValidationError(
            "source attempt manifest must be a schema-version 1 validation run snapshot"
        )
    run_id = str(payload.get("run_id", ""))
    owners = [bundle for bundle in bundles if bundle.run_id == run_id]
    if len(owners) != 1:
        raise MergeValidationError(
            f"source attempt manifest run_id does not identify one merge input: {run_id!r}"
        )
    owner = owners[0]
    if payload.get("project_commit") != str(owner.frame["project_commit"].iloc[0]):
        raise MergeValidationError("source attempt manifest project_commit disagrees")
    if payload.get("split_manifest") != owner.run_manifest.get("split_manifest") or payload.get(
        "split_manifest_sha256"
    ) != owner.run_manifest.get("split_manifest_sha256"):
        raise MergeValidationError("source attempt manifest validation split disagrees")
    declared_methods = payload.get("methods")
    high_density_methods = payload.get("high_density_methods")
    if not isinstance(declared_methods, list) or not isinstance(high_density_methods, list):
        raise MergeValidationError("source attempt manifest has invalid method lists")
    if (
        frozenset(str(value) for value in (*declared_methods, *high_density_methods))
        != owner.methods
    ):
        raise MergeValidationError("source attempt manifest method set disagrees")
    expected = len(owner.frame)
    if payload.get("expected_task_count") != expected:
        raise MergeValidationError("source attempt manifest expected-task count disagrees")
    records = payload.get("results")
    if not isinstance(records, list) or len(records) != expected:
        raise MergeValidationError("source attempt manifest must retain every logical task record")
    if any(not isinstance(record, Mapping) for record in records):
        raise MergeValidationError("source attempt manifest result records must be mappings")
    task_indices = [int(record.get("task_index", -1)) for record in records]
    if len(task_indices) != len(set(task_indices)):
        raise MergeValidationError("source attempt manifest reuses a task_index")
    statuses = Counter(str(record.get("status", "")) for record in records)
    if set(statuses) - {"complete", "error"}:
        raise MergeValidationError(
            f"source attempt manifest has unknown task statuses: {dict(statuses)!r}"
        )
    completed = int(statuses.get("complete", 0))
    if payload.get("completed_task_count") != completed:
        raise MergeValidationError("source attempt manifest completed-task count disagrees")
    owner_by_task = owner.frame.set_index("task_index", drop=False)
    no_outcome_keys: list[str] = []
    other_error_count = 0
    for record in records:
        task_index = int(record.get("task_index", -1))
        if task_index not in owner_by_task.index:
            raise MergeValidationError(
                f"source attempt manifest contains an unknown task_index: {task_index}"
            )
        row = owner_by_task.loc[task_index]
        if (
            str(record.get("method", "")) != str(row["source_policy"])
            or str(record.get("scenario_id", "")) != str(row["scenario_id"])
            or int(record.get("replicate", -1)) != int(row["replicate"])
        ):
            raise MergeValidationError(
                f"source attempt manifest logical-task metadata disagrees at {task_index}"
            )
        if record.get("status") == "complete":
            episode_id = str(record.get("episode_id", ""))
            attempts = record.get("attempts")
            if (
                episode_id != str(row["episode_id"])
                or not isinstance(attempts, list)
                or not attempts
                or not isinstance(attempts[-1], Mapping)
                or str(attempts[-1].get("episode_id", "")) != episode_id
                or str(attempts[-1].get("outcome", "")) != str(row["outcome"])
            ):
                raise MergeValidationError(
                    f"source attempt manifest completed outcome disagrees at {task_index}"
                )
        if record.get("status") != "error":
            continue
        error_text = str(record.get("error", ""))
        no_outcome = (
            record.get("episode_id") in (None, "")
            and record.get("attempts") == []
            and "without outcome" in error_text.lower()
        )
        if no_outcome:
            no_outcome_keys.append(f"{run_id}:{task_index}:{error_text}")
        else:
            other_error_count += 1
    worker_errors = payload.get("worker_errors")
    if not isinstance(worker_errors, list):
        raise MergeValidationError("source attempt manifest worker_errors must be a list")
    try:
        requested_jobs = int(payload["requested_jobs"])
        effective_jobs = int(payload["effective_jobs"])
    except (KeyError, TypeError, ValueError) as error:
        raise MergeValidationError("source attempt manifest has invalid job counts") from error
    if requested_jobs <= 0 or effective_jobs <= 0:
        raise MergeValidationError("source attempt manifest job counts must be positive")
    return AttemptManifestEvidence(
        path=resolved,
        sha256=sha256_file(resolved),
        run_id=run_id,
        status_counts=dict(sorted(statuses.items())),
        expected_task_count=expected,
        completed_task_count=completed,
        no_outcome_error_count=len(no_outcome_keys),
        other_error_count=other_error_count,
        worker_error_count=len(worker_errors),
        requested_jobs=requested_jobs,
        effective_jobs=effective_jobs,
        no_outcome_keys=tuple(no_outcome_keys),
    )


def _validate_input_pair(bundles: Sequence[InputBundle]) -> str:
    if len(bundles) != 2:
        raise MergeValidationError("exactly two collected result inputs are required")
    method_sets = [bundle.methods for bundle in bundles]
    if method_sets[0] & method_sets[1]:
        raise MergeValidationError("input method sets must be disjoint")
    if frozenset().union(*method_sets) != METHOD_SET:
        raise MergeValidationError(f"merged methods must be exactly {list(METHODS)!r}")
    if set(method_sets) != {BASE_METHODS, OTHER_METHODS}:
        raise MergeValidationError(
            "inputs must be one Base-only table and one standard/heuristic/bc_uniform/pgrr table"
        )
    commits = {
        _one_string(bundle.frame, "project_commit", label=str(bundle.results_path))
        for bundle in bundles
    }
    if len(commits) != 1:
        raise MergeValidationError(
            f"inputs must share one project_commit; observed={sorted(commits)!r}"
        )
    run_ids = {bundle.run_id for bundle in bundles}
    if len(run_ids) != 2:
        raise MergeValidationError("source run manifests must have distinct run_id values")
    split_paths = {str(bundle.run_manifest["split_manifest"]) for bundle in bundles}
    split_hashes = {str(bundle.run_manifest["split_manifest_sha256"]) for bundle in bundles}
    if len(split_paths) != 1 or len(split_hashes) != 1:
        raise MergeValidationError("source runs disagree on the frozen validation split")
    columns = [tuple(bundle.frame.columns) for bundle in bundles]
    if columns[0] != columns[1]:
        raise MergeValidationError("input result schemas use different column order or membership")
    dtypes = [tuple(str(dtype) for dtype in bundle.frame.dtypes) for bundle in bundles]
    if dtypes[0] != dtypes[1]:
        raise MergeValidationError("input result schemas use different column dtypes")
    return next(iter(commits))


def _validate_merged_pairs(merged: pd.DataFrame) -> None:
    if len(merged) != EXPECTED_ROWS:
        raise MergeValidationError(f"merged results require exactly {EXPECTED_ROWS} rows")
    if merged["episode_id"].astype(str).duplicated().any():
        raise MergeValidationError("episode_id values must be globally unique across source runs")
    duplicate = merged.duplicated(subset=["source_policy", "pair_id"], keep=False)
    if bool(duplicate.any()):
        raise MergeValidationError("merged results contain duplicate method/pair rows")
    method_counts = merged.groupby("source_policy", observed=True).size().to_dict()
    expected_counts = {method: EXPECTED_CONDITIONS for method in METHODS}
    if method_counts != expected_counts:
        raise MergeValidationError(
            f"merged method counts disagree with the 360-row contract: {method_counts!r}"
        )
    pair_counts = merged.groupby("pair_id", observed=True).size()
    if len(pair_counts) != EXPECTED_CONDITIONS or not bool(pair_counts.eq(len(METHODS)).all()):
        raise MergeValidationError(
            f"merged results require {EXPECTED_CONDITIONS} complete five-method pairs"
        )
    present_shared = [column for column in PAIR_SHARED_COLUMNS if column in merged.columns]
    missing_shared = sorted(set(REQUIRED_SHARED_COLUMNS) - set(present_shared))
    if missing_shared:
        raise MergeValidationError(f"merged results are missing shared fields: {missing_shared}")
    for pair_id, group in merged.groupby("pair_id", sort=False, dropna=False):
        observed_methods = set(group["source_policy"].astype(str))
        if observed_methods != METHOD_SET:
            raise MergeValidationError(
                f"pair {pair_id!r} does not contain exactly the five registered methods"
            )
        for column in present_shared:
            tokens = group[column].map(moderate_artifacts._metadata_token)
            if int(tokens.nunique(dropna=False)) != 1:
                values = sorted(set(tokens.astype(str)))
                raise MergeValidationError(
                    "pair metadata mismatch across methods; "
                    f"pair_id={pair_id!r}, column={column}, values={values!r}"
                )


def merge_frames(bundles: Sequence[InputBundle]) -> tuple[pd.DataFrame, str]:
    """Return a deterministic five-method frame after every merge gate passes."""

    commit = _validate_input_pair(bundles)
    merged = pd.concat([bundle.frame for bundle in bundles], ignore_index=True, sort=False)
    _validate_merged_pairs(merged)
    order = {method: index for index, method in enumerate(METHODS)}
    merged["_merge_method_order"] = merged["source_policy"].map(order)
    merged = (
        merged.sort_values(["pair_id", "_merge_method_order"], kind="stable")
        .drop(columns="_merge_method_order")
        .reset_index(drop=True)
    )
    return merged, commit


def _temporary_path(destination: Path, *, suffix: str) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=suffix,
        dir=destination.parent,
    )
    os.close(descriptor)
    return Path(raw_path)


def _attempt_record(evidence: AttemptManifestEvidence, project_root: Path) -> dict[str, Any]:
    return {
        "path": _display_path(evidence.path, project_root),
        "sha256": evidence.sha256,
        "run_id": evidence.run_id,
        "status_counts": evidence.status_counts,
        "expected_task_count": evidence.expected_task_count,
        "completed_task_count": evidence.completed_task_count,
        "no_outcome_error_count": evidence.no_outcome_error_count,
        "other_error_count": evidence.other_error_count,
        "worker_error_count": evidence.worker_error_count,
        "requested_jobs": evidence.requested_jobs,
        "effective_jobs": evidence.effective_jobs,
        "algorithm_outcomes_added_to_results": 0,
    }


def _input_record(
    bundle: InputBundle,
    project_root: Path,
    attempt_manifests: Sequence[AttemptManifestEvidence],
) -> dict[str, Any]:
    method_order = [method for method in METHODS if method in bundle.methods]
    return {
        "results_path": _display_path(bundle.results_path, project_root),
        "results_sha256": bundle.results_sha256,
        "row_count": len(bundle.frame),
        "methods": method_order,
        "run_manifest_path": _display_path(bundle.run_manifest_path, project_root),
        "run_manifest_sha256": bundle.run_manifest_sha256,
        "run_id": bundle.run_id,
        "episode_manifest": str(bundle.run_manifest["episode_manifest"]),
        "split_manifest": str(bundle.run_manifest["split_manifest"]),
        "split_manifest_sha256": str(bundle.run_manifest["split_manifest_sha256"]),
        "requested_jobs": int(bundle.run_manifest["requested_jobs"]),
        "effective_jobs": int(bundle.run_manifest["effective_jobs"]),
        "source_attempt_manifests": [
            _attempt_record(evidence, project_root)
            for evidence in attempt_manifests
            if evidence.run_id == bundle.run_id
        ],
    }


def write_merged_outputs(
    *,
    bundles: Sequence[InputBundle],
    output_path: Path,
    merge_manifest_path: Path,
    attempt_manifests: Sequence[AttemptManifestEvidence] = (),
    project_root: Path = ROOT,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Validate, stage, and atomically replace the merged Parquet and merge manifest."""

    output = output_path.resolve()
    merge_manifest = merge_manifest_path.resolve()
    input_paths = {
        path
        for bundle in bundles
        for path in (bundle.results_path.resolve(), bundle.run_manifest_path.resolve())
    }
    input_paths.update(evidence.path.resolve() for evidence in attempt_manifests)
    if output in input_paths or merge_manifest in input_paths:
        raise MergeValidationError("merge outputs must not overwrite a source artifact")
    if output == merge_manifest:
        raise MergeValidationError("Parquet output and merge manifest must be different files")
    if merge_manifest.name == "run_manifest.json":
        raise MergeValidationError("merge provenance must not be named run_manifest.json")
    attempt_paths = [evidence.path.resolve() for evidence in attempt_manifests]
    if len(attempt_paths) != len(set(attempt_paths)):
        raise MergeValidationError("source attempt manifest paths must be unique")
    attempt_hashes = [evidence.sha256 for evidence in attempt_manifests]
    if len(attempt_hashes) != len(set(attempt_hashes)):
        raise MergeValidationError("duplicate source attempt manifest content")
    known_run_ids = {bundle.run_id for bundle in bundles}
    if any(evidence.run_id not in known_run_ids for evidence in attempt_manifests):
        raise MergeValidationError("source attempt manifest does not belong to a merge input")

    merged, commit = merge_frames(bundles)
    ordered_bundles = sorted(bundles, key=lambda bundle: 0 if bundle.methods == BASE_METHODS else 1)
    parquet_temporary: Path | None = None
    manifest_temporary: Path | None = None
    try:
        parquet_temporary = _temporary_path(output, suffix=".parquet.tmp")
        manifest_temporary = _temporary_path(merge_manifest, suffix=".json.tmp")
        merged.to_parquet(parquet_temporary, index=False)
        output_sha256 = sha256_file(parquet_temporary)
        payload: dict[str, Any] = {
            "schema_version": 1,
            "artifact_type": "validation_results_merge",
            "split": "validation",
            "project_commit": commit,
            "methods": list(METHODS),
            "condition_count": EXPECTED_CONDITIONS,
            "row_count": EXPECTED_ROWS,
            "source_run_count": 2,
            "source_run_ids": [bundle.run_id for bundle in ordered_bundles],
            "shared_condition_columns": [
                column for column in PAIR_SHARED_COLUMNS if column in merged.columns
            ],
            "inputs": [
                _input_record(bundle, project_root, attempt_manifests) for bundle in ordered_bundles
            ],
            "output": {
                "results_path": _display_path(output, project_root),
                "results_sha256": output_sha256,
                "row_count": len(merged),
            },
            "provenance_policy": {
                "synthetic_run_manifest_created": False,
                "source_run_manifests_preserved": True,
                "source_run_manifests_are_final_completeness_snapshots": True,
                "source_run_manifests_claim_complete_attempt_history": False,
                "attempt_manifest_records_are_not_algorithm_outcomes": True,
                "condition_filtering": False,
            },
            "technical_attempt_provenance": {
                "attempt_manifest_count": len(attempt_manifests),
                "no_outcome_error_record_count": sum(
                    evidence.no_outcome_error_count for evidence in attempt_manifests
                ),
                "unique_no_outcome_error_record_count": len(
                    {key for evidence in attempt_manifests for key in evidence.no_outcome_keys}
                ),
                "other_error_record_count": sum(
                    evidence.other_error_count for evidence in attempt_manifests
                ),
                "algorithm_outcomes_added_to_results": 0,
                "history_status": "supplied" if attempt_manifests else "not_supplied",
            },
        }
        manifest_temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        parquet_temporary.replace(output)
        manifest_temporary.replace(merge_manifest)
    finally:
        if parquet_temporary is not None:
            parquet_temporary.unlink(missing_ok=True)
        if manifest_temporary is not None:
            manifest_temporary.unlink(missing_ok=True)
    return merged, payload


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        action="append",
        required=True,
        type=Path,
        help="Collected validation results.parquet; provide exactly twice.",
    )
    parser.add_argument(
        "--run-manifest",
        action="append",
        type=Path,
        default=None,
        help="Matching real run_manifest.json; provide twice or omit for sibling defaults.",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--merge-manifest", type=Path, default=None)
    parser.add_argument(
        "--attempt-manifest",
        action="append",
        type=Path,
        default=[],
        help=(
            "Optional preserved pre-resume run snapshot. Repeat as needed; errors are "
            "recorded as technical provenance and never merged as algorithm outcomes."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if len(args.results) != 2:
            raise MergeValidationError("--results must be provided exactly twice")
        run_paths = args.run_manifest
        if run_paths is None:
            run_paths = [path.with_name("run_manifest.json") for path in args.results]
        if len(run_paths) != 2:
            raise MergeValidationError("--run-manifest must be omitted or provided exactly twice")
        merge_manifest_path = args.merge_manifest or args.output.with_name("merge_manifest.json")
        bundles = [
            load_input_bundle(results_path, run_path)
            for results_path, run_path in zip(args.results, run_paths, strict=True)
        ]
        attempt_manifests = [load_attempt_manifest(path, bundles) for path in args.attempt_manifest]
        _, payload = write_merged_outputs(
            bundles=bundles,
            output_path=args.output,
            merge_manifest_path=merge_manifest_path,
            attempt_manifests=attempt_manifests,
        )
        print(
            "Validation merge PASS: "
            f"{payload['row_count']} rows, {payload['condition_count']} complete pairs, "
            f"runs={','.join(payload['source_run_ids'])}"
        )
        return 0
    except (MergeValidationError, KeyError, TypeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
