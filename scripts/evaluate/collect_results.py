#!/usr/bin/env python3
"""Collect immutable episode artifacts into the final evaluation tables.

The manifest is the authority for which episodes belong to an evaluation.  A
missing artifact is therefore an error rather than an episode that can be
silently dropped.  Simulator failures and invalid resets are retained in the
result table and counted explicitly, but are excluded from algorithm rates and
paired hypothesis tests.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import sys
from collections.abc import Mapping, Sequence
from itertools import pairwise
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd

EXCLUDED_OUTCOMES = frozenset({"SIMULATOR_FAILURE", "INVALID_RESET"})
KNOWN_OUTCOMES = frozenset(
    {
        "GOAL_REACHED",
        "COLLISION",
        "TIMEOUT",
        "PLANNER_FAILURE",
        *EXCLUDED_OUTCOMES,
    }
)
CONTINUE_ACTION_ID = 24
NORMAL_STATE = 0
REJOIN_STATE = 3
EMERGENCY_STATE = 4
RECOVERY_STATES = frozenset({1, 2, 3})
PERSONAL_SPACE_M = 1.2
DISCOMFORT_DISTANCE_M = 1.0
STATE_NAMES = {
    0: "NORMAL",
    1: "PENDING_RECOVERY",
    2: "RECOVERY",
    3: "REJOIN",
    4: "EMERGENCY_STOP",
    5: "FAILED",
    6: "SUCCEEDED",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSON at {path}:{line_number}: {error}") from error
        if not isinstance(row, dict):
            raise ValueError(f"expected a JSON object at {path}:{line_number}")
        rows.append(row)
    return rows


def _float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        return None
    result = float(value)
    return result if not math.isnan(result) else None


def _xy(value: object) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple, np.ndarray)) or len(value) < 2:
        return None
    x = _float(value[0])
    y = _float(value[1])
    if x is None or y is None or not math.isfinite(x) or not math.isfinite(y):
        return None
    return x, y


def _polyline_length(points: object) -> float | None:
    if not isinstance(points, (list, tuple, np.ndarray)) or len(points) < 2:
        return None
    coordinates = [_xy(point) for point in points]
    if any(point is None for point in coordinates):
        return None
    valid = [point for point in coordinates if point is not None]
    return float(sum(math.dist(first, second) for first, second in pairwise(valid)))


def _timestamps(rows: Sequence[Mapping[str, Any]], stream_path: Path) -> np.ndarray:
    values: list[float] = []
    for index, row in enumerate(rows):
        timestamp = _float(row.get("timestamp"))
        if timestamp is None or not math.isfinite(timestamp):
            raise ValueError(f"missing or invalid timestamp in {stream_path} row {index}")
        values.append(timestamp)
    result = np.asarray(values, dtype=np.float64)
    if result.size > 1 and np.any(np.diff(result) < 0.0):
        raise ValueError(f"timestamps are not monotonic in {stream_path}")
    return result


def _duration_where(timestamps: np.ndarray, condition: np.ndarray) -> float:
    if timestamps.size < 2:
        return 0.0
    intervals = np.maximum(np.diff(timestamps), 0.0)
    return float(np.sum(intervals * condition[:-1].astype(np.float64)))


def _entry_count(condition: np.ndarray) -> int:
    if condition.size == 0:
        return 0
    previous = np.concatenate((np.asarray([False]), condition[:-1]))
    return int(np.count_nonzero(condition & ~previous))


def _human_metrics(rows: Sequence[Mapping[str, Any]], timestamps: np.ndarray) -> dict[str, float]:
    distances: list[float] = []
    available: list[bool] = []
    for row in rows:
        privileged = row.get("privileged")
        value = privileged.get("nearest_human_distance") if isinstance(privileged, dict) else None
        distance = _float(value)
        is_available = distance is not None and distance >= 0.0
        distances.append(distance if is_available else math.nan)
        available.append(is_available)

    distance_array = np.asarray(distances, dtype=np.float64)
    available_array = np.asarray(available, dtype=np.bool_)
    finite = distance_array[np.isfinite(distance_array)]
    minimum = float(np.min(finite)) if finite.size else math.nan

    if timestamps.size < 2:
        if not available_array.size or not available_array[0]:
            return {
                "min_human_distance_m": minimum,
                "human_distance_coverage_ratio": math.nan,
                "personal_space_violation_ratio": math.nan,
                "discomfort_time_s": math.nan,
            }
        return {
            "min_human_distance_m": minimum,
            "human_distance_coverage_ratio": 1.0,
            "personal_space_violation_ratio": float(distance_array[0] < PERSONAL_SPACE_M),
            "discomfort_time_s": 0.0,
        }

    intervals = np.maximum(np.diff(timestamps), 0.0)
    total_duration = float(np.sum(intervals))
    observed_duration = float(np.sum(intervals * available_array[:-1]))
    if observed_duration <= 0.0:
        personal_ratio = math.nan
        discomfort_duration = math.nan
    else:
        personal_duration = float(
            np.sum(intervals * available_array[:-1] * (distance_array[:-1] < PERSONAL_SPACE_M))
        )
        discomfort_duration = float(
            np.sum(intervals * available_array[:-1] * (distance_array[:-1] < DISCOMFORT_DISTANCE_M))
        )
        personal_ratio = personal_duration / observed_duration
    coverage = observed_duration / total_duration if total_duration > 0.0 else math.nan
    return {
        "min_human_distance_m": minimum,
        "human_distance_coverage_ratio": coverage,
        "personal_space_violation_ratio": personal_ratio,
        "discomfort_time_s": discomfort_duration,
    }


def _pose(row: Mapping[str, Any], *, physical: bool) -> tuple[float, float] | None:
    if physical:
        privileged = row.get("privileged")
        if not isinstance(privileged, dict):
            return None
        return _xy(privileged.get("robot_pose"))
    return _xy(row.get("robot_pose"))


def _path_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, float | str]:
    physical = [_pose(row, physical=True) for row in rows]
    localized = [_pose(row, physical=False) for row in rows]
    if physical and all(point is not None for point in physical):
        poses = [point for point in physical if point is not None]
        source = "physical_pose"
    elif localized and all(point is not None for point in localized):
        poses = [point for point in localized if point is not None]
        source = "localized_pose"
    else:
        poses = []
        source = "unavailable"
    length = float(sum(math.dist(a, b) for a, b in pairwise(poses))) if poses else math.nan

    errors = [
        math.dist(actual, estimate)
        for actual, estimate in zip(physical, localized, strict=True)
        if actual is not None and estimate is not None
    ]
    return {
        "path_length_m": length,
        "path_pose_source": source,
        "max_localization_error_m": max(errors) if errors else math.nan,
    }


def _shortest_path_length(
    manifest_row: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]
) -> tuple[float, str]:
    declared = _float(manifest_row.get("shortest_path_length_m"))
    if declared is not None and math.isfinite(declared) and declared >= 0.0:
        return declared, "manifest"
    if rows:
        planned = _polyline_length(rows[0].get("global_path"))
        if planned is not None and planned > 0.0:
            return planned, "initial_global_path"
        start = _pose(rows[0], physical=True) or _pose(rows[0], physical=False)
        goal = _xy(rows[0].get("goal"))
        if start is not None and goal is not None:
            return math.dist(start, goal), "straight_line_fallback"
    return math.nan, "unavailable"


def _angular_jerk(rows: Sequence[Mapping[str, Any]], timestamps: np.ndarray) -> float:
    if len(rows) < 3:
        return math.nan
    angular_velocity: list[float] = []
    for row in rows:
        velocity = row.get("robot_velocity")
        omega = (
            _float(velocity[1])
            if isinstance(velocity, (list, tuple)) and len(velocity) > 1
            else None
        )
        if omega is None or not math.isfinite(omega):
            return math.nan
        angular_velocity.append(omega)
    omega_array = np.asarray(angular_velocity, dtype=np.float64)
    dt = np.diff(timestamps)
    valid = dt > 0.0
    if np.count_nonzero(valid) < 2:
        return math.nan
    acceleration = np.diff(omega_array)[valid] / dt[valid]
    acceleration_times = ((timestamps[:-1] + timestamps[1:]) / 2.0)[valid]
    jerk_dt = np.diff(acceleration_times)
    jerk_valid = jerk_dt > 0.0
    if not np.any(jerk_valid):
        return math.nan
    jerk = np.diff(acceleration)[jerk_valid] / jerk_dt[jerk_valid]
    weights = jerk_dt[jerk_valid]
    return float(np.average(np.abs(jerk), weights=weights))


def _control_metrics(
    rows: Sequence[Mapping[str, Any]], timestamps: np.ndarray
) -> dict[str, float | int]:
    states = np.asarray([int(row.get("recovery_state", 0)) for row in rows], dtype=np.int64)
    actions = np.asarray(
        [int(row.get("recovery_action", CONTINUE_ACTION_ID)) for row in rows],
        dtype=np.int64,
    )
    emergency = states == EMERGENCY_STATE
    recovery = np.isin(states, tuple(RECOVERY_STATES))
    recovery_active = recovery | emergency
    non_continue = actions != CONTINUE_ACTION_ID
    command_override: list[bool] = []
    for row in rows:
        command = row.get("cmd_vel")
        base_command = row.get("base_cmd_vel")
        if (
            isinstance(command, (list, tuple))
            and isinstance(base_command, (list, tuple))
            and len(command) >= 2
            and len(base_command) >= 2
        ):
            values = [
                _float(command[0]),
                _float(command[1]),
                _float(base_command[0]),
                _float(base_command[1]),
            ]
            override = all(value is not None for value in values) and (
                abs(float(values[0]) - float(values[2])) > 1.0e-6
                or abs(float(values[1]) - float(values[3])) > 1.0e-6
            )
        else:
            override = False
        command_override.append(override)
    intervention = recovery_active | non_continue | np.asarray(command_override)
    duration = float(timestamps[-1] - timestamps[0]) if timestamps.size > 1 else 0.0
    intervention_duration = _duration_where(timestamps, intervention)
    recovery_trigger_count = _entry_count(recovery_active)
    # A recovery succeeds when REJOIN hands control back to NORMAL after the
    # original goal has been restored and valid progress resumes.  State 6 is
    # the terminal navigation success state, not a recovery-sequence success;
    # counting it here would conflate reaching the task goal with rejoining.
    recovery_success_count = int(
        np.count_nonzero((states[:-1] == REJOIN_STATE) & (states[1:] == NORMAL_STATE))
    )
    return {
        "emergency_stop_count": _entry_count(emergency),
        "emergency_sample_count": int(np.count_nonzero(emergency)),
        "emergency_duration_s": _duration_where(timestamps, emergency),
        "recovery_trigger_count": recovery_trigger_count,
        "recovery_success_count": recovery_success_count,
        "recovery_success_rate": (
            recovery_success_count / recovery_trigger_count
            if recovery_trigger_count > 0
            else math.nan
        ),
        "recovery_action_sample_count": int(np.count_nonzero(non_continue)),
        "recovery_duration_s": _duration_where(timestamps, recovery_active),
        "intervention_count": _entry_count(intervention),
        "intervention_sample_count": int(np.count_nonzero(intervention)),
        "intervention_duration_s": intervention_duration,
        "intervention_ratio": intervention_duration / duration if duration > 0.0 else 0.0,
        "mean_abs_angular_jerk_rad_s3": _angular_jerk(rows, timestamps),
    }


def _timeline(
    rows: Sequence[Mapping[str, Any]], timestamps: np.ndarray
) -> dict[str, list[float] | list[str] | None]:
    if timestamps.size < 2:
        return {
            "timeline_time_s": None,
            "timeline_failure_score": None,
            "timeline_distance_to_goal_m": None,
            "timeline_recovery_state": None,
        }
    failure = np.asarray([_float(row.get("failure_score")) for row in rows], dtype=object)
    distance = np.asarray([_float(row.get("distance_to_goal")) for row in rows], dtype=object)
    if any(value is None or not math.isfinite(float(value)) for value in failure) or any(
        value is None or not math.isfinite(float(value)) for value in distance
    ):
        return {
            "timeline_time_s": None,
            "timeline_failure_score": None,
            "timeline_distance_to_goal_m": None,
            "timeline_recovery_state": None,
        }
    keep = np.concatenate((np.asarray([True]), np.diff(timestamps) > 0.0))
    states = [
        STATE_NAMES.get(int(row.get("recovery_state", 0)), str(row.get("recovery_state", 0)))
        for row in rows
    ]
    return {
        "timeline_time_s": timestamps[keep].astype(float).tolist(),
        "timeline_failure_score": np.asarray(failure[keep], dtype=float).tolist(),
        "timeline_distance_to_goal_m": np.asarray(distance[keep], dtype=float).tolist(),
        "timeline_recovery_state": [
            state for state, retain in zip(states, keep, strict=True) if retain
        ],
    }


def _scenario_fields(scenario_id: str) -> tuple[str, str | None, str | None]:
    pattern = (
        r"^(?P<family>.+)_(?P<density>low|medium|high)_"
        r"(?P<split>train|validation|test)_"
    )
    match = re.match(pattern, scenario_id)
    if match is None:
        return scenario_id, None, None
    return match.group("family"), match.group("density"), match.group("split")


def _terminal_goal_distance(outcome: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> float:
    declared = _float(outcome.get("physical_goal_distance_m"))
    if declared is not None and math.isfinite(declared):
        return declared
    if not rows:
        return math.nan
    goal = _xy(rows[-1].get("goal"))
    robot = _pose(rows[-1], physical=True) or _pose(rows[-1], physical=False)
    return math.dist(goal, robot) if goal is not None and robot is not None else math.nan


def _normalize_policy(value: object) -> str:
    policy = str(value).strip()
    return "bc" if policy == "dagger" else policy


def collect_episode(
    manifest_row: Mapping[str, Any],
    raw_dir: Path,
    *,
    episode_id_override: str | None = None,
    attempts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Collect one manifest episode without dropping an invalid terminal outcome."""

    logical_episode_id = str(manifest_row.get("episode_id", "")).strip()
    episode_id = str(episode_id_override or logical_episode_id).strip()
    if not episode_id:
        raise ValueError("manifest row has no episode_id")
    prefix = raw_dir / episode_id
    stream_path = prefix.with_suffix(".jsonl")
    metadata_path = prefix.with_suffix(".metadata.json")
    outcome_path = prefix.with_suffix(".outcome.json")
    missing = [path for path in (stream_path, metadata_path, outcome_path) if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            f"episode {episode_id} is missing required artifacts: "
            + ", ".join(str(path) for path in missing)
        )

    metadata = _read_json_object(metadata_path)
    outcome_payload = _read_json_object(outcome_path)
    if (
        metadata.get("episode_id") != episode_id
        or outcome_payload.get("episode_id", episode_id) != episode_id
    ):
        raise ValueError(f"artifact episode_id does not match manifest: {episode_id}")
    outcome = str(outcome_payload.get("outcome", "")).strip()
    if outcome not in KNOWN_OUTCOMES:
        raise ValueError(f"unknown outcome for {episode_id}: {outcome!r}")
    excluded = outcome in EXCLUDED_OUTCOMES
    rows = _read_jsonl(stream_path)
    if not rows and not excluded:
        raise ValueError(f"algorithm episode has an empty stream: {stream_path}")
    timestamps = _timestamps(rows, stream_path) if rows else np.asarray([], dtype=np.float64)

    scenario_id = str(metadata.get("scenario_id", manifest_row.get("scenario_id", "")))
    manifest_scenario_id = manifest_row.get("scenario_id")
    if manifest_scenario_id and str(manifest_scenario_id) != scenario_id:
        raise ValueError(f"scenario_id mismatch for {episode_id}")
    manifest_seed = manifest_row.get("seed")
    if manifest_seed is not None and int(manifest_seed) != int(metadata.get("seed", -1)):
        raise ValueError(f"seed mismatch for {episode_id}")
    manifest_commit = manifest_row.get("project_commit")
    if manifest_commit and str(manifest_commit) != str(metadata.get("project_commit", "")):
        raise ValueError(f"project_commit mismatch for {episode_id}")
    family, inferred_density, inferred_split = _scenario_fields(scenario_id)
    manifest_policy = manifest_row.get("source_policy", manifest_row.get("method", ""))
    source_policy = _normalize_policy(metadata.get("source_policy", manifest_policy))
    if not source_policy:
        raise ValueError(f"episode {episode_id} has no source_policy")
    if manifest_policy and _normalize_policy(manifest_policy) != source_policy:
        raise ValueError(f"source_policy mismatch for {episode_id}")

    effective_attempts: Sequence[Mapping[str, Any]] = attempts or (
        {"attempt": 0, "episode_id": episode_id, "outcome": outcome, "resumed": False},
    )
    excluded_attempts = [
        {
            "attempt": int(attempt.get("attempt", index)),
            "episode_id": str(attempt.get("episode_id", "")),
            "outcome": str(attempt.get("outcome", "")),
            "resumed": bool(attempt.get("resumed", False)),
        }
        for index, attempt in enumerate(effective_attempts)
        if str(attempt.get("outcome", "")) in EXCLUDED_OUTCOMES
    ]

    result = dict(manifest_row)
    duration = float(timestamps[-1]) if timestamps.size else math.nan
    if timestamps.size:
        path_metrics = _path_metrics(rows)
        human_metrics = _human_metrics(rows, timestamps)
        control_metrics = _control_metrics(rows, timestamps)
        timeline = _timeline(rows, timestamps)
        shortest_path, shortest_source = _shortest_path_length(manifest_row, rows)
        path_length = float(path_metrics["path_length_m"])
        if outcome == "GOAL_REACHED" and math.isfinite(shortest_path) and shortest_path >= 0.0:
            denominator = (
                max(path_length, shortest_path) if math.isfinite(path_length) else math.nan
            )
            spl = shortest_path / denominator if denominator > 0.0 else 1.0
        else:
            spl = 0.0
        progress_start = _float(rows[0].get("distance_to_goal"))
        progress_end = _float(rows[-1].get("distance_to_goal"))
        progress = (
            progress_start - progress_end
            if progress_start is not None and progress_end is not None
            else math.nan
        )
        lidar = [_float(row.get("nearest_obstacle_distance")) for row in rows]
        finite_lidar = [value for value in lidar if value is not None and math.isfinite(value)]
        min_lidar = min(finite_lidar) if finite_lidar else math.nan
    else:
        path_metrics = {
            "path_length_m": math.nan,
            "path_pose_source": "unavailable",
            "max_localization_error_m": math.nan,
        }
        human_metrics = {
            "min_human_distance_m": math.nan,
            "human_distance_coverage_ratio": math.nan,
            "personal_space_violation_ratio": math.nan,
            "discomfort_time_s": math.nan,
        }
        control_metrics = {
            "emergency_stop_count": 0,
            "emergency_sample_count": 0,
            "emergency_duration_s": 0.0,
            "recovery_trigger_count": 0,
            "recovery_success_count": 0,
            "recovery_success_rate": math.nan,
            "recovery_action_sample_count": 0,
            "recovery_duration_s": 0.0,
            "intervention_count": 0,
            "intervention_sample_count": 0,
            "intervention_duration_s": 0.0,
            "intervention_ratio": math.nan,
            "mean_abs_angular_jerk_rad_s3": math.nan,
        }
        timeline = {
            "timeline_time_s": None,
            "timeline_failure_score": None,
            "timeline_distance_to_goal_m": None,
            "timeline_recovery_state": None,
        }
        shortest_path, shortest_source, spl, progress, min_lidar = (
            math.nan,
            "unavailable",
            math.nan,
            math.nan,
            math.nan,
        )

    result.update(
        {
            "episode_id": episode_id,
            "logical_episode_id": logical_episode_id,
            "scenario_id": scenario_id,
            "family": str(manifest_row.get("family", family)),
            "density": manifest_row.get("density", inferred_density),
            "split": metadata.get("split", manifest_row.get("split", inferred_split)),
            "seed": int(metadata.get("seed", manifest_row.get("seed", -1))),
            "source_policy": source_policy,
            "planner_id": metadata.get("planner_id"),
            "project_commit": metadata.get("project_commit"),
            "arena_commit": metadata.get("arena_commit"),
            "outcome": outcome,
            "outcome_detail": outcome_payload.get("detail", ""),
            "included_in_algorithm_metrics": not excluded,
            "exclusion_reason": outcome if excluded else "",
            "physical_attempt_count": len(effective_attempts),
            "excluded_attempt_count": len(excluded_attempts),
            "simulator_failure_attempt_count": sum(
                attempt["outcome"] == "SIMULATOR_FAILURE" for attempt in excluded_attempts
            ),
            "invalid_reset_attempt_count": sum(
                attempt["outcome"] == "INVALID_RESET" for attempt in excluded_attempts
            ),
            "excluded_attempts_json": json.dumps(excluded_attempts, sort_keys=True),
            "success": outcome == "GOAL_REACHED",
            "collision": outcome == "COLLISION",
            "timeout": outcome == "TIMEOUT",
            "planner_failure": outcome == "PLANNER_FAILURE",
            "sample_count": len(rows),
            "outcome_sample_count": outcome_payload.get("sample_count"),
            "episode_duration_s": duration,
            "navigation_time_s": duration,
            "progress_m": progress,
            "terminal_physical_goal_distance_m": _terminal_goal_distance(outcome_payload, rows),
            "shortest_path_length_m": shortest_path,
            "shortest_path_source": shortest_source,
            "spl": spl,
            "min_lidar_m": min_lidar,
            "raw_sha256": _sha256(stream_path),
            "metadata_sha256": _sha256(metadata_path),
            "outcome_sha256": _sha256(outcome_path),
            **path_metrics,
            **human_metrics,
            **control_metrics,
            **timeline,
        }
    )
    return result


def _run_manifest_results(path: Path, manifest: pd.DataFrame) -> dict[int, dict[str, Any]]:
    payload = _read_json_object(path)
    records = payload.get("results")
    if not isinstance(records, list):
        raise ValueError(f"run manifest has no results list: {path}")
    if payload.get("worker_errors"):
        raise ValueError(f"run manifest contains worker errors: {path}")
    indexed: dict[int, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError(f"run manifest result is not an object: {path}")
        task_index = int(record.get("task_index", -1))
        if task_index in indexed:
            raise ValueError(f"duplicate task_index in run manifest: {task_index}")
        if record.get("status") != "complete" or not record.get("episode_id"):
            raise ValueError(f"incomplete task in run manifest: {task_index}")
        indexed[task_index] = record
    expected = set(int(value) for value in manifest["task_index"])
    if set(indexed) != expected:
        raise ValueError(
            "run manifest task indices differ from episode manifest: "
            f"missing={sorted(expected - set(indexed))}, "
            f"unexpected={sorted(set(indexed) - expected)}"
        )
    return indexed


def collect_results(
    manifest_path: Path,
    raw_dir: Path,
    run_manifest_path: Path | None = None,
) -> pd.DataFrame:
    """Collect every unique row in a Parquet episode manifest."""

    manifest = pd.read_parquet(manifest_path)
    if "episode_id" not in manifest.columns:
        raise ValueError("episode manifest must contain episode_id")
    if manifest.empty:
        raise ValueError("episode manifest is empty")
    if manifest["episode_id"].isna().any() or manifest["episode_id"].astype(str).duplicated().any():
        raise ValueError("episode_id values must be non-null and unique")
    resolved_run_manifest = run_manifest_path
    if resolved_run_manifest is None:
        candidate = manifest_path.with_name("run_manifest.json")
        resolved_run_manifest = candidate if candidate.is_file() else None
    run_results: dict[int, dict[str, Any]] = {}
    if resolved_run_manifest is not None:
        if "task_index" not in manifest.columns:
            raise ValueError("task_index is required when a run manifest is used")
        run_results = _run_manifest_results(resolved_run_manifest, manifest)

    records: list[dict[str, Any]] = []
    actual_episode_ids: set[str] = set()
    for row in manifest.to_dict(orient="records"):
        run_record = run_results.get(int(row["task_index"])) if run_results else None
        actual_episode_id = str(run_record["episode_id"]) if run_record is not None else None
        if actual_episode_id is not None and actual_episode_id in actual_episode_ids:
            raise ValueError(f"run manifest reuses physical episode_id: {actual_episode_id}")
        if actual_episode_id is not None:
            actual_episode_ids.add(actual_episode_id)
        attempts = run_record.get("attempts", []) if run_record is not None else []
        if not isinstance(attempts, list):
            raise ValueError(f"attempts must be a list for {actual_episode_id}")
        records.append(
            collect_episode(
                row,
                raw_dir,
                episode_id_override=actual_episode_id,
                attempts=attempts,
            )
        )
    return pd.DataFrame.from_records(records)


SUMMARY_METRICS = (
    "episode_duration_s",
    "path_length_m",
    "spl",
    "min_human_distance_m",
    "personal_space_violation_ratio",
    "discomfort_time_s",
    "emergency_stop_count",
    "recovery_trigger_count",
    "recovery_success_rate",
    "intervention_ratio",
    "mean_abs_angular_jerk_rad_s3",
)


def _project_commit(results: pd.DataFrame) -> str:
    commits = sorted(str(value) for value in results["project_commit"].dropna().unique())
    if len(commits) != 1 or not commits[0]:
        raise ValueError(f"final results must use exactly one project commit: {commits}")
    return commits[0]


def build_summary(results: pd.DataFrame) -> pd.DataFrame:
    """Build method rows in the union summary schema."""

    summaries: list[dict[str, Any]] = []
    project_commit = _project_commit(results)
    for source_policy, group in results.groupby("source_policy", dropna=False, sort=True):
        valid = group[group["included_in_algorithm_metrics"].astype(bool)]
        count = len(valid)
        row: dict[str, Any] = {
            "row_type": "method_summary",
            "project_commit": project_commit,
            "source_policy": source_policy,
            "method": source_policy,
            "manifest_episode_count": len(group),
            "algorithm_episode_count": count,
            "excluded_episode_count": len(group) - count,
            "physical_attempt_count": int(
                pd.to_numeric(group["physical_attempt_count"], errors="coerce").fillna(1).sum()
            ),
            "excluded_attempt_count": int(
                pd.to_numeric(group["excluded_attempt_count"], errors="coerce").fillna(0).sum()
            ),
            "simulator_failure_count": int(
                pd.to_numeric(group["simulator_failure_attempt_count"], errors="coerce")
                .fillna(0)
                .sum()
            ),
            "invalid_reset_count": int(
                pd.to_numeric(group["invalid_reset_attempt_count"], errors="coerce").fillna(0).sum()
            ),
        }
        for outcome in ("GOAL_REACHED", "COLLISION", "TIMEOUT", "PLANNER_FAILURE"):
            key = outcome.lower()
            outcome_count = int((valid["outcome"] == outcome).sum())
            row[f"{key}_count"] = outcome_count
            row[f"{key}_rate"] = outcome_count / count if count else math.nan
            if outcome == "GOAL_REACHED":
                row["success_count"] = outcome_count
                row["success_rate"] = outcome_count / count if count else math.nan
        for metric in SUMMARY_METRICS:
            values = pd.to_numeric(valid[metric], errors="coerce").dropna()
            row[f"{metric}_mean"] = float(values.mean()) if len(values) else math.nan
            row[f"{metric}_std"] = float(values.std(ddof=1)) if len(values) > 1 else math.nan
            row[f"{metric}_median"] = float(values.median()) if len(values) else math.nan
        summaries.append(row)
    return pd.DataFrame.from_records(summaries)


def _paired_test_rows(
    statistics_payload: Mapping[str, Any],
    *,
    project_commit: str,
) -> list[dict[str, Any]]:
    reference = str(statistics_payload["reference_policy"])
    treatment = str(statistics_payload["treatment_policy"])
    labels = {"base": "DWB", "bc": "Triggered DAgger"}
    comparison = f"{labels.get(reference, reference)} vs {labels.get(treatment, treatment)}"
    rows: list[dict[str, Any]] = []
    for metric, analysis_value in statistics_payload.get("binary_outcomes", {}).items():
        if not isinstance(analysis_value, dict):
            continue
        difference = analysis_value.get("difference_treatment_minus_reference")
        test = analysis_value.get("mcnemar_exact")
        if not isinstance(difference, dict) or not isinstance(test, dict):
            continue
        rows.append(
            {
                "row_type": "statistic",
                "project_commit": project_commit,
                "comparison": comparison,
                # Keep stable machine-readable metric keys in summary.csv.
                # Presentation scripts map these keys to human labels.
                "metric": metric,
                "test": "McNemar exact",
                "estimate": difference["estimate"],
                "ci_low": difference["lower"],
                "ci_high": difference["upper"],
                "p_value": test["pvalue_raw"],
                "p_value_holm": test["pvalue_holm"],
                "effect_size": test["matched_odds_ratio_haldane"],
                "n_pairs": analysis_value["pair_count"],
                "population": "all_valid_pairs",
            }
        )
    for metric, analysis_value in statistics_payload.get("continuous_metrics", {}).items():
        if not isinstance(analysis_value, dict) or analysis_value.get("status") != "ok":
            continue
        difference = analysis_value.get("difference_treatment_minus_reference")
        test = analysis_value.get("wilcoxon")
        effect = analysis_value.get("effect_size")
        if (
            not isinstance(difference, dict)
            or not isinstance(test, dict)
            or not isinstance(effect, dict)
        ):
            continue
        rows.append(
            {
                "row_type": "statistic",
                "project_commit": project_commit,
                "comparison": comparison,
                "metric": metric,
                "test": "Wilcoxon signed-rank",
                "estimate": difference["estimate"],
                "ci_low": difference["lower"],
                "ci_high": difference["upper"],
                "p_value": test["pvalue_raw"],
                "p_value_holm": test["pvalue_holm"],
                "effect_size": effect["rank_biserial_correlation"],
                "n_pairs": analysis_value["pair_count"],
                "population": analysis_value["population"],
            }
        )
    return rows


def build_union_summary(
    results: pd.DataFrame,
    statistics_payload: Mapping[str, Any],
) -> pd.DataFrame:
    """Combine method aggregates and flattened paired tests without losing either."""

    method_rows = build_summary(results)
    test_rows = pd.DataFrame.from_records(
        _paired_test_rows(statistics_payload, project_commit=_project_commit(results))
    )
    return pd.concat((method_rows, test_rows), ignore_index=True, sort=False)


def _load_statistics_module() -> ModuleType:
    path = Path(__file__).with_name("statistics.py")
    spec = importlib.util.spec_from_file_location("ramp_final_statistics", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load statistics implementation: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_outputs(
    *,
    manifest_path: Path,
    raw_dir: Path,
    run_manifest_path: Path | None,
    results_path: Path,
    summary_path: Path,
    statistics_path: Path,
    reference_policy: str,
    treatment_policy: str,
    bootstrap_samples: int,
    bootstrap_seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Collect results and atomically replace the three derived artifacts."""

    if reference_policy == treatment_policy:
        raise ValueError(
            "reference_policy and treatment_policy must differ; use collection-only "
            "for a single-method run"
        )
    results = collect_results(manifest_path, raw_dir, run_manifest_path)
    statistics_module = _load_statistics_module()
    statistics_payload: dict[str, Any] = statistics_module.build_statistics(
        results,
        reference_policy=reference_policy,
        treatment_policy=treatment_policy,
        bootstrap_samples=bootstrap_samples,
        bootstrap_seed=bootstrap_seed,
    )
    summary = build_union_summary(results, statistics_payload)
    for path in (results_path, summary_path, statistics_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    results.to_parquet(results_path, index=False)
    summary.to_csv(summary_path, index=False, lineterminator="\n")
    statistics_path.write_text(
        json.dumps(statistics_payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return results, summary, statistics_payload


def _atomic_write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def _atomic_write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, lineterminator="\n")
    temporary.replace(path)


def write_collection_outputs(
    *,
    manifest_path: Path,
    raw_dir: Path,
    run_manifest_path: Path | None,
    results_path: Path,
    summary_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Collect immutable episodes without inventing a single-method comparison.

    This is the only supported output path for a one-method calibration run.
    Retryable simulator/reset attempts remain embedded in the episode rows and
    method summary, while no pairwise-statistics artifact is created.
    """

    results = collect_results(manifest_path, raw_dir, run_manifest_path)
    summary = build_summary(results)
    _atomic_write_parquet(results, results_path)
    _atomic_write_csv(summary, summary_path)
    return results, summary


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=Path("outputs/final/episode_manifest.parquet")
    )
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--run-manifest",
        type=Path,
        default=None,
        help="Runner record; defaults to run_manifest.json beside the episode manifest if present.",
    )
    parser.add_argument("--results", type=Path, default=Path("outputs/final/results.parquet"))
    parser.add_argument("--summary", type=Path, default=Path("outputs/final/summary.csv"))
    parser.add_argument("--statistics", type=Path, default=Path("outputs/final/statistics.json"))
    parser.add_argument("--reference-policy", default="base")
    parser.add_argument("--treatment-policy", default="bc")
    parser.add_argument("--bootstrap-samples", type=int, default=10_000)
    parser.add_argument("--bootstrap-seed", type=int, default=0)
    parser.add_argument(
        "--collection-only",
        action="store_true",
        help=(
            "write results and method summary only; required for a single-method run and "
            "never emits pairwise statistics"
        ),
    )
    args = parser.parse_args(argv)
    if args.collection_only:
        write_collection_outputs(
            manifest_path=args.manifest,
            raw_dir=args.raw_dir,
            run_manifest_path=args.run_manifest,
            results_path=args.results,
            summary_path=args.summary,
        )
        return
    write_outputs(
        manifest_path=args.manifest,
        raw_dir=args.raw_dir,
        run_manifest_path=args.run_manifest,
        results_path=args.results,
        summary_path=args.summary,
        statistics_path=args.statistics,
        reference_policy=args.reference_policy,
        treatment_policy=args.treatment_policy,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed,
    )


if __name__ == "__main__":
    main()
