#!/usr/bin/env python3
# ruff: noqa: RUF001
"""Build stage-aware report assets without consulting unapproved results.

The default ``pending`` stage is deliberately result-data free. Result-bearing
stages require a completed episode-level Parquet, its sibling
``pairwise_statistics.json``, and a hash-linked matched-run telemetry sidecar.
Historical, pilot, calibration, smoke, rejected v5, and live validation paths
are rejected before a result file is opened.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from collections.abc import Mapping, Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_NAME = (
    "PGRR: Planning-Guided Failure-Triggered Recovery and Rejoin for Dynamic Social Navigation"
)
BENCHMARK_ID = "moderate_social_navigation_v6"
MATCHED_EVIDENCE_FILENAME = "matched_base_pgrr_evidence.json"
MATCHED_TRAJECTORY_FILENAME = "moderate_matched_base_pgrr_trajectory.pdf"
MATCHED_TIMELINE_FILENAME = "moderate_pgrr_recovery_timeline.pdf"
MATCHED_TEST_SELECTION_RULE = (
    "eligible: PGRR trigger + configured static geometry + actor routes; order: "
    "Base failure/PGRR goal, outcome contrast, PGRR goal, density, trigger count, "
    "family, seed, pair_id"
)
METHODS = ("base", "standard", "heuristic", "bc_uniform", "pgrr")
METHOD_LABELS = {
    "base": "DWB",
    "standard": "Standard",
    "heuristic": "Heuristic",
    "bc_uniform": "Uniform BC",
    "pgrr": "PGRR",
}
COMPARATORS = METHODS[:-1]
OUTCOMES = ("GOAL_REACHED", "COLLISION", "TIMEOUT", "PLANNER_FAILURE")
EXCLUDED_OUTCOMES = ("SIMULATOR_FAILURE", "INVALID_RESET")
DENSITIES = ("low", "medium", "high")
FAMILIES = (
    "head_on_corridor",
    "doorway_bottleneck",
    "crossing_flow",
    "blind_corner",
    "group_blocking",
    "overtaking",
    "opposite_streams",
    "temporary_blockage",
)

METHOD_COLORS = {
    "base": "#4D5963",
    "standard": "#8A959E",
    "heuristic": "#356E9F",
    "bc_uniform": "#78A9CC",
    "pgrr": "#D55E00",
}
OUTCOME_COLORS = {
    "GOAL_REACHED": "#356E9F",
    "COLLISION": "#D55E00",
    "TIMEOUT": "#78A9CC",
    "PLANNER_FAILURE": "#7A7F85",
}
ENDPOINTS = (
    ("goal_reached", "GOAL_REACHED", "目标到达", "#356E9F", "正值有利"),
    ("collision", "COLLISION", "碰撞", "#D55E00", "负值有利"),
    ("timeout", "TIMEOUT", "超时", "#7A7F85", "负值有利"),
)
FORBIDDEN_RESULT_PARTS = (
    "/outputs/final/",
    "/old64/",
    "/pilot/",
    "/calibration",
    "/smoke/",
    "/outputs/moderate/v5_validation/",
    "/outputs/moderate/v5_validation_",
    "/outputs/moderate/v6_validation",
)


class ReportInputError(RuntimeError):
    """Raised when report inputs are incomplete, stale, or outside policy."""


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _validate_artifact_path(
    path: Path,
    *,
    stage: str,
    project_root: Path,
    filename: str,
    kind: str,
) -> Path:
    """Resolve one report artifact and reject every non-authoritative location."""

    resolved = path.expanduser().resolve()
    normalized = resolved.as_posix()
    if any(token in normalized for token in FORBIDDEN_RESULT_PARTS):
        raise ReportInputError(
            "result path is forbidden: historical, pilot, calibration, smoke, "
            "and live validation outputs may not feed reports"
        )
    if resolved.name != filename:
        raise ReportInputError(f"the {kind} input must be named {filename}")

    if stage == "test":
        allowed = (project_root / "outputs/moderate/final").resolve()
    elif stage == "validation":
        allowed = (project_root / "outputs/report_inputs/validation").resolve()
    else:
        raise ReportInputError(f"stage {stage!r} must not receive a result path")
    if not _inside(resolved, allowed):
        raise ReportInputError(
            f"{stage} reports only accept {kind} inputs under {allowed.relative_to(project_root)}"
        )
    if not resolved.is_file():
        raise ReportInputError(f"completed report input does not exist: {resolved}")
    return resolved


def validate_result_path(path: Path, *, stage: str, project_root: Path) -> Path:
    """Resolve a result path and reject every non-authoritative location."""

    return _validate_artifact_path(
        path,
        stage=stage,
        project_root=project_root,
        filename="results.parquet",
        kind="result",
    )


def validate_statistics_path(path: Path, *, stage: str, project_root: Path) -> Path:
    """Resolve the paired-statistics path under the same fail-closed policy."""

    return _validate_artifact_path(
        path,
        stage=stage,
        project_root=project_root,
        filename="pairwise_statistics.json",
        kind="statistics",
    )


def validate_matched_evidence_path(path: Path, *, stage: str, project_root: Path) -> Path:
    """Resolve the matched raw-telemetry sidecar under the same path policy."""

    return _validate_artifact_path(
        path,
        stage=stage,
        project_root=project_root,
        filename=MATCHED_EVIDENCE_FILENAME,
        kind="matched evidence",
    )


def validate_runtime_capture(project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """Verify the tracked Gazebo GUI pixels against their capture metadata.

    This qualitative frozen-scene demonstration is deliberately independent of
    the result stage. It must never be labelled as a camera frame from the
    locked v6 statistical run.
    """

    screenshot = project_root / "outputs/figures/runtime/gazebo_doorway_bottleneck_medium.png"
    paper_copy = project_root / "paper/figures/runtime_gazebo_doorway_bottleneck_medium.png"
    metadata_path = (
        project_root / "outputs/figures/runtime/gazebo_doorway_bottleneck_medium.metadata.json"
    )
    window_path = (
        project_root / "outputs/figures/runtime/gazebo_doorway_bottleneck_medium.window.json"
    )
    required = (screenshot, paper_copy, metadata_path, window_path)
    missing = [path.relative_to(project_root).as_posix() for path in required if not path.is_file()]
    if missing:
        raise ReportInputError(f"verified Gazebo runtime evidence is incomplete: {missing}")
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("artifact_type") != (
        "real_arena_gazebo_gui_screenshot"
    ):
        raise ReportInputError("runtime metadata does not declare a real Gazebo GUI screenshot")
    artifacts = payload.get("artifacts")
    launch = payload.get("launch_profile")
    scenario = payload.get("scenario")
    if not all(isinstance(value, Mapping) for value in (artifacts, launch, scenario)):
        raise ReportInputError("runtime metadata omits artifacts, launch profile, or scenario")
    assert isinstance(artifacts, Mapping)
    assert isinstance(launch, Mapping)
    assert isinstance(scenario, Mapping)
    declared_sha = str(artifacts.get("screenshot_sha256", ""))
    if len(declared_sha) != 64 or _sha256(screenshot) != declared_sha:
        raise ReportInputError("runtime screenshot SHA256 disagrees with capture metadata")
    if _sha256(paper_copy) != declared_sha:
        raise ReportInputError("paper-facing runtime screenshot is not the verified pixel copy")
    if (
        str(launch.get("simulator", "")).lower() != "gazebo"
        or str(launch.get("robot", "")).lower() != "jackal"
        or str(launch.get("local_planner", "")).lower() != "dwb"
    ):
        raise ReportInputError("runtime screenshot must come from Gazebo/Jackal/Nav2 DWB")
    if scenario.get("split") != "validation" or "moderate_v5" not in str(
        scenario.get("scenario_id", "")
    ):
        raise ReportInputError("runtime screenshot must remain the audited frozen-v5 demo")
    if payload.get("capture_target") != "Gazebo GUI window":
        raise ReportInputError("runtime screenshot metadata does not identify the Gazebo window")
    for field in ("episode_id", "episode_outcome", "git_commit", "arena_commit"):
        if not str(payload.get(field, "")).strip():
            raise ReportInputError(f"runtime screenshot metadata omits {field}")
    if str(payload["episode_outcome"]) not in OUTCOMES:
        raise ReportInputError("runtime screenshot metadata contains an unknown episode outcome")
    if len(str(payload["git_commit"])) != 40 or len(str(payload["arena_commit"])) != 40:
        raise ReportInputError("runtime screenshot metadata contains an invalid Git revision")
    note = str(payload.get("provenance_note", ""))
    if "same Arena/Nav2 episode" not in note:
        raise ReportInputError("runtime screenshot is not bound to its declared episode record")
    window = json.loads(window_path.read_text(encoding="utf-8"))
    selected_window = window.get("selected_window") if isinstance(window, dict) else None
    if not isinstance(selected_window, Mapping) or str(selected_window.get("title")) != "Gazebo":
        raise ReportInputError("runtime window provenance is invalid")
    return payload


def _runtime_capture_summary(payload: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    metadata_path = (
        project_root / "outputs/figures/runtime/gazebo_doorway_bottleneck_medium.metadata.json"
    )
    scenario = payload["scenario"]
    artifacts = payload["artifacts"]
    assert isinstance(scenario, Mapping)
    assert isinstance(artifacts, Mapping)
    return {
        "available": True,
        "artifact_type": str(payload["artifact_type"]),
        "representation": "real Gazebo GUI screenshot from a frozen validation demo",
        "not_locked_statistical_episode": True,
        "episode_id": str(payload["episode_id"]),
        "episode_outcome": str(payload["episode_outcome"]),
        "scenario_id": str(scenario["scenario_id"]),
        "split": str(scenario["split"]),
        "git_commit": str(payload["git_commit"]),
        "arena_commit": str(payload["arena_commit"]),
        "screenshot_sha256": str(artifacts["screenshot_sha256"]),
        "metadata_sha256": _sha256(metadata_path),
    }


def _tex_escape(value: object) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_rows(results: pd.DataFrame) -> pd.DataFrame:
    return results.loc[_valid_mask(results)].copy()


def _valid_mask(results: pd.DataFrame) -> pd.Series:
    expected = ~results["outcome"].isin(EXCLUDED_OUTCOMES)
    if "included_in_algorithm_metrics" not in results:
        return expected
    declared = results["included_in_algorithm_metrics"]
    if not pd.api.types.is_bool_dtype(declared.dtype):
        if not bool(declared.isin((True, False)).all()):
            raise ReportInputError("included_in_algorithm_metrics must be boolean")
    declared_bool = declared.astype(bool)
    if not bool(declared_bool.eq(expected).all()):
        raise ReportInputError(
            "included_in_algorithm_metrics disagrees with infrastructure exclusion semantics"
        )
    return declared_bool


def validate_results(
    results: pd.DataFrame,
    *,
    stage: str,
    expected_conditions: int,
) -> None:
    required = {
        "episode_id",
        "pair_id",
        "scenario_id",
        "family",
        "density",
        "replicate",
        "seed",
        "split",
        "source_policy",
        "outcome",
        "raw_sha256",
        "scenario_sha256",
        "episode_duration_s",
        "navigation_time_s",
        "path_length_m",
        "min_human_distance_m",
        "recovery_trigger_count",
        "recovery_success_count",
        "recovery_duration_s",
        "intervention_ratio",
    }
    missing = sorted(required - set(results.columns))
    if missing:
        raise ReportInputError(f"results.parquet is missing columns: {missing}")
    if results.empty:
        raise ReportInputError("results.parquet is empty")
    observed_splits = set(results["split"].astype(str))
    if observed_splits != {stage}:
        raise ReportInputError(
            f"stage {stage!r} requires exactly split={stage!r}; found {sorted(observed_splits)}"
        )
    observed_methods = set(results["source_policy"].astype(str))
    if observed_methods != set(METHODS):
        raise ReportInputError(
            f"the complete five-method protocol is required; found {sorted(observed_methods)}"
        )
    scenario_ids = results["scenario_id"].astype(str)
    pair_ids = results["pair_id"].astype(str)
    if not bool(scenario_ids.str.contains("_moderate_v6_").all()) or not bool(
        pair_ids.str.contains("_moderate_v6_").all()
    ):
        raise ReportInputError(
            "report inputs must belong to moderate-v6; rejected v5 results cannot be copied "
            "into an approved snapshot"
        )
    known = set(OUTCOMES) | set(EXCLUDED_OUTCOMES)
    unknown = sorted(set(results["outcome"].astype(str)) - known)
    if unknown:
        raise ReportInputError(f"unknown terminal outcomes: {unknown}")
    if results["pair_id"].isna().any():
        raise ReportInputError("every report row requires a non-null pair_id")
    if results["pair_id"].astype(str).str.strip().eq("").any():
        raise ReportInputError("every report row requires a non-empty pair_id")
    _valid_mask(results)
    groups = results.groupby("pair_id", sort=False, dropna=False)
    if groups.ngroups != expected_conditions:
        raise ReportInputError(
            f"expected {expected_conditions} paired conditions, found {groups.ngroups}"
        )
    for pair_id, group in groups:
        methods = tuple(sorted(group["source_policy"].astype(str)))
        if len(group) != len(METHODS) or set(methods) != set(METHODS):
            raise ReportInputError(
                f"pair {pair_id!r} does not contain exactly one row for every method"
            )
        for column in ("scenario_id", "family", "density", "replicate", "seed", "split"):
            if group[column].astype(str).nunique(dropna=False) != 1:
                raise ReportInputError(
                    f"pair metadata differs across methods: pair={pair_id!r}, column={column}"
                )


def _probability(value: object, *, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ReportInputError(f"statistics {field} must be a probability") from error
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ReportInputError(f"statistics {field} must be a finite probability")
    return number


def _finite(value: object, *, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ReportInputError(f"statistics {field} must be finite") from error
    if not math.isfinite(number):
        raise ReportInputError(f"statistics {field} must be finite")
    return number


def _integer(value: object, *, field: str) -> int:
    if isinstance(value, bool):
        raise ReportInputError(f"statistics {field} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ReportInputError(f"statistics {field} must be an integer") from error
    try:
        same_value = float(value) == number
    except (TypeError, ValueError):
        same_value = False
    if not same_value or number < 0:
        raise ReportInputError(f"statistics {field} must be a non-negative integer")
    return number


def _holm_adjust(pvalues: Mapping[str, float]) -> dict[str, float]:
    ordered = sorted(pvalues.items(), key=lambda item: (item[1], item[0]))
    adjusted: dict[str, float] = {}
    running = 0.0
    total = len(ordered)
    for index, (name, pvalue) in enumerate(ordered):
        running = max(running, min(1.0, (total - index) * pvalue))
        adjusted[name] = running
    return adjusted


def _exact_mcnemar_pvalue(reference_only: int, treatment_only: int) -> float:
    discordant = reference_only + treatment_only
    if discordant == 0:
        return 1.0
    tail = sum(
        math.comb(discordant, index) for index in range(min(reference_only, treatment_only) + 1)
    )
    return min(1.0, 2.0 * tail / (2**discordant))


def _global_holm_evidence(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    global_tests = payload.get("global_multiple_comparison")
    if not isinstance(global_tests, Mapping) or global_tests.get("method") != "Holm":
        raise ReportInputError("statistics must contain one global Holm comparison family")
    rows = global_tests.get("hypotheses")
    if not isinstance(rows, list) or not rows:
        raise ReportInputError("statistics global Holm family is empty")
    declared_count = _integer(
        global_tests.get("hypothesis_count"), field="global Holm hypothesis_count"
    )
    if declared_count != len(rows):
        raise ReportInputError("statistics global Holm hypothesis count is inconsistent")
    evidence: dict[str, dict[str, Any]] = {}
    raw: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ReportInputError("statistics global Holm hypothesis rows must be objects")
        name = str(row.get("hypothesis", "")).strip()
        if not name or name in evidence:
            raise ReportInputError("statistics global Holm hypothesis names must be unique")
        raw[name] = _probability(row.get("pvalue_raw"), field=f"{name} raw p")
        _probability(row.get("pvalue_holm_global"), field=f"{name} Holm p")
        evidence[name] = row
    expected_adjusted = _holm_adjust(raw)
    for name, expected in expected_adjusted.items():
        observed = float(evidence[name]["pvalue_holm_global"])
        if not math.isclose(observed, expected, rel_tol=1.0e-12, abs_tol=1.0e-12):
            raise ReportInputError(f"statistics global Holm adjustment is inconsistent for {name}")
    return evidence


def validate_statistics(
    payload: object,
    *,
    results: pd.DataFrame,
    expected_conditions: int,
) -> list[dict[str, Any]]:
    """Cross-check every reported binary effect against the approved Parquet."""

    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise ReportInputError("pairwise_statistics.json does not contain successful statistics")
    if payload.get("main_method") != "pgrr" or payload.get("reference_method") != "base":
        raise ReportInputError("statistics must compare every baseline against PGRR")
    if list(payload.get("methods", [])) != list(METHODS):
        raise ReportInputError("statistics method order does not match the five-method protocol")
    if list(payload.get("comparators", [])) != list(COMPARATORS):
        raise ReportInputError("statistics must cover all four baselines in protocol order")

    policy = payload.get("analysis_policy")
    if not isinstance(policy, Mapping):
        raise ReportInputError("statistics omit analysis_policy provenance")
    if bool(policy.get("scenario_or_seed_filtering", True)):
        raise ReportInputError("statistics must prohibit scenario/seed filtering")
    for field, expected in (
        ("condition_count", expected_conditions),
        ("method_count", len(METHODS)),
        ("manifest_episode_count", expected_conditions * len(METHODS)),
    ):
        observed = _integer(policy.get(field), field=f"analysis_policy.{field}")
        if observed != expected:
            raise ReportInputError(
                f"statistics {field} disagrees with results: "
                f"expected={expected}, observed={observed}"
            )

    comparisons = payload.get("comparisons")
    if not isinstance(comparisons, Mapping) or set(comparisons) != set(COMPARATORS):
        raise ReportInputError("statistics comparisons do not cover exactly all four baselines")
    bootstrap = payload.get("bootstrap")
    if not isinstance(bootstrap, Mapping):
        raise ReportInputError("statistics omit bootstrap provenance")
    bootstrap_samples = _integer(bootstrap.get("samples"), field="bootstrap.samples")
    if bootstrap_samples <= 0:
        raise ReportInputError("statistics bootstrap sample count must be positive")
    global_evidence = _global_holm_evidence(payload)
    pgrr = results.loc[results["source_policy"] == "pgrr", ["pair_id", "outcome"]].copy()
    pgrr["valid"] = ~pgrr["outcome"].isin(EXCLUDED_OUTCOMES)

    records: list[dict[str, Any]] = []
    for comparator in COMPARATORS:
        comparison = comparisons[comparator]
        if not isinstance(comparison, Mapping) or comparison.get("status") != "ok":
            raise ReportInputError(f"statistics comparison {comparator} is not successful")
        if (
            comparison.get("reference_policy") != comparator
            or comparison.get("treatment_policy") != "pgrr"
            or comparison.get("direction") != f"pgrr_minus_{comparator}"
        ):
            raise ReportInputError(f"statistics direction is invalid for {comparator}")
        if list(comparison.get("pairing_columns", [])) != ["pair_id"]:
            raise ReportInputError(f"statistics must pair {comparator} by immutable pair_id")
        if (
            _integer(
                comparison.get("manifest_episode_count"),
                field=f"{comparator}.manifest_episode_count",
            )
            != 2 * expected_conditions
        ):
            raise ReportInputError(f"statistics manifest episode count disagrees for {comparator}")
        comparison_bootstrap = comparison.get("bootstrap")
        if (
            not isinstance(comparison_bootstrap, Mapping)
            or _integer(
                comparison_bootstrap.get("samples"), field=f"{comparator}.bootstrap.samples"
            )
            != bootstrap_samples
        ):
            raise ReportInputError(f"statistics bootstrap provenance disagrees for {comparator}")

        reference = results.loc[
            results["source_policy"] == comparator, ["pair_id", "outcome"]
        ].copy()
        reference["valid"] = ~reference["outcome"].isin(EXCLUDED_OUTCOMES)
        paired = reference.merge(
            pgrr,
            on="pair_id",
            validate="one_to_one",
            suffixes=("_reference", "_treatment"),
        )
        if len(paired) != expected_conditions:
            raise ReportInputError(f"statistics pairing lost conditions for {comparator}")
        complete = paired.loc[paired["valid_reference"] & paired["valid_treatment"]].copy()
        pair_count = len(complete)
        if (
            _integer(comparison.get("valid_pair_count"), field=f"{comparator}.valid_pair_count")
            != pair_count
        ):
            raise ReportInputError(f"statistics valid-pair count disagrees for {comparator}")
        expected_excluded = expected_conditions - pair_count
        if (
            _integer(
                comparison.get("excluded_pair_count"), field=f"{comparator}.excluded_pair_count"
            )
            != expected_excluded
        ):
            raise ReportInputError(f"statistics excluded-pair count disagrees for {comparator}")

        binary = comparison.get("binary_outcomes")
        if not isinstance(binary, Mapping):
            raise ReportInputError(f"statistics omit binary outcomes for {comparator}")
        for endpoint_key, outcome, endpoint_label, _color, _direction in ENDPOINTS:
            endpoint = binary.get(endpoint_key)
            if not isinstance(endpoint, Mapping):
                raise ReportInputError(f"statistics omit {comparator}/{endpoint_key}")
            if (
                _integer(
                    endpoint.get("pair_count"), field=f"{comparator}/{endpoint_key}.pair_count"
                )
                != pair_count
            ):
                raise ReportInputError(
                    f"statistics pair count disagrees for {comparator}/{endpoint_key}"
                )

            reference_indicator = (complete["outcome_reference"] == outcome).astype(int)
            treatment_indicator = (complete["outcome_treatment"] == outcome).astype(int)
            reference_count = int(reference_indicator.sum())
            treatment_count = int(treatment_indicator.sum())
            reference_rate = reference_count / pair_count
            treatment_rate = treatment_count / pair_count
            deterministic = {
                "reference_count": float(reference_count),
                "treatment_count": float(treatment_count),
                "reference_rate": reference_rate,
                "treatment_rate": treatment_rate,
            }
            for field, expected in deterministic.items():
                observed = _finite(
                    endpoint.get(field), field=f"{comparator}/{endpoint_key}.{field}"
                )
                if not math.isclose(observed, expected, rel_tol=1.0e-12, abs_tol=1.0e-12):
                    raise ReportInputError(
                        f"statistics {field} disagrees for {comparator}/{endpoint_key}"
                    )

            interval = endpoint.get("difference_treatment_minus_reference")
            if not isinstance(interval, Mapping):
                raise ReportInputError(
                    f"statistics omit paired difference for {comparator}/{endpoint_key}"
                )
            estimate = _finite(
                interval.get("estimate"), field=f"{comparator}/{endpoint_key}.estimate"
            )
            lower = _finite(interval.get("lower"), field=f"{comparator}/{endpoint_key}.lower")
            upper = _finite(interval.get("upper"), field=f"{comparator}/{endpoint_key}.upper")
            confidence = _probability(
                interval.get("confidence"), field=f"{comparator}/{endpoint_key}.confidence"
            )
            if not math.isclose(confidence, 0.95, abs_tol=1.0e-12):
                raise ReportInputError("statistics must use 95% paired bootstrap intervals")
            if (
                _integer(
                    interval.get("bootstrap_samples"),
                    field=f"{comparator}/{endpoint_key}.bootstrap_samples",
                )
                != bootstrap_samples
            ):
                raise ReportInputError(
                    f"statistics bootstrap sample count disagrees for {comparator}/{endpoint_key}"
                )
            expected_difference = treatment_rate - reference_rate
            if not math.isclose(estimate, expected_difference, rel_tol=1.0e-12, abs_tol=1.0e-12):
                raise ReportInputError(
                    f"statistics paired difference disagrees for {comparator}/{endpoint_key}"
                )
            if not -1.0 <= lower <= estimate <= upper <= 1.0:
                raise ReportInputError(f"invalid paired interval for {comparator}/{endpoint_key}")

            test = endpoint.get("mcnemar_exact")
            if not isinstance(test, Mapping):
                raise ReportInputError(
                    f"statistics omit McNemar test for {comparator}/{endpoint_key}"
                )
            reference_only = int(((reference_indicator == 1) & (treatment_indicator == 0)).sum())
            treatment_only = int(((reference_indicator == 0) & (treatment_indicator == 1)).sum())
            discordant = reference_only + treatment_only
            for field, expected in (
                ("reference_only", reference_only),
                ("treatment_only", treatment_only),
                ("discordant_pairs", discordant),
            ):
                if (
                    _integer(test.get(field), field=f"{comparator}/{endpoint_key}.{field}")
                    != expected
                ):
                    raise ReportInputError(
                        f"statistics McNemar cells disagree for {comparator}/{endpoint_key}"
                    )
            raw_p = _probability(test.get("pvalue_raw"), field=f"{comparator}/{endpoint_key}.raw p")
            expected_raw_p = _exact_mcnemar_pvalue(reference_only, treatment_only)
            if not math.isclose(raw_p, expected_raw_p, rel_tol=1.0e-12, abs_tol=1.0e-12):
                raise ReportInputError(
                    f"statistics raw McNemar p disagrees for {comparator}/{endpoint_key}"
                )
            holm_p = _probability(
                test.get("pvalue_holm"), field=f"{comparator}/{endpoint_key}.Holm p"
            )
            odds_ratio = _finite(
                test.get("matched_odds_ratio_haldane"),
                field=f"{comparator}/{endpoint_key}.matched odds ratio",
            )
            expected_odds_ratio = (treatment_only + 0.5) / (reference_only + 0.5)
            if odds_ratio <= 0.0 or not math.isclose(
                odds_ratio, expected_odds_ratio, rel_tol=1.0e-12, abs_tol=1.0e-12
            ):
                raise ReportInputError(
                    f"statistics matched odds ratio disagrees for {comparator}/{endpoint_key}"
                )

            hypothesis = f"{comparator}::mcnemar_{endpoint_key}"
            global_row = global_evidence.get(hypothesis)
            if (
                global_row is None
                or global_row.get("comparator") != comparator
                or global_row.get("test") != f"mcnemar_{endpoint_key}"
            ):
                raise ReportInputError(f"statistics global Holm row is missing for {hypothesis}")
            if not math.isclose(
                float(global_row["pvalue_raw"]), raw_p, rel_tol=1.0e-12, abs_tol=1.0e-12
            ) or not math.isclose(
                float(global_row["pvalue_holm_global"]),
                holm_p,
                rel_tol=1.0e-12,
                abs_tol=1.0e-12,
            ):
                raise ReportInputError(f"statistics global Holm row disagrees for {hypothesis}")

            records.append(
                {
                    "comparator": comparator,
                    "comparator_label": METHOD_LABELS[comparator],
                    "endpoint": endpoint_key,
                    "endpoint_label": endpoint_label,
                    "pair_count": pair_count,
                    "reference_rate": reference_rate,
                    "treatment_rate": treatment_rate,
                    "difference": estimate,
                    "ci_lower": lower,
                    "ci_upper": upper,
                    "pvalue_raw": raw_p,
                    "pvalue_holm": holm_p,
                    "matched_odds_ratio_haldane": odds_ratio,
                    "discordant_pairs": discordant,
                }
            )
    return records


def validate_joint_success_efficiency(
    payload: object,
    *,
    results: pd.DataFrame,
    expected_conditions: int,
) -> dict[str, Any]:
    """Cross-check Base--PGRR joint-success efficiency against Parquet and JSON."""

    if not isinstance(payload, Mapping):
        raise ReportInputError("pairwise statistics must be an object")
    comparisons = payload.get("comparisons")
    if not isinstance(comparisons, Mapping):
        raise ReportInputError("pairwise statistics omit comparisons")
    base_comparison = comparisons.get("base")
    if not isinstance(base_comparison, Mapping):
        raise ReportInputError("pairwise statistics omit the Base--PGRR comparison")
    continuous = base_comparison.get("continuous_metrics")
    if not isinstance(continuous, Mapping):
        raise ReportInputError("pairwise statistics omit Base--PGRR continuous metrics")
    bootstrap = payload.get("bootstrap")
    if not isinstance(bootstrap, Mapping):
        raise ReportInputError("pairwise statistics omit bootstrap provenance")
    bootstrap_samples = _integer(bootstrap.get("samples"), field="bootstrap.samples")
    global_evidence = _global_holm_evidence(payload)

    working = results.copy()
    working["_valid"] = _valid_mask(working)
    columns = (
        "pair_id",
        "outcome",
        "_valid",
        "episode_duration_s",
        "path_length_m",
    )
    reference = working.loc[working["source_policy"] == "base", list(columns)]
    treatment = working.loc[working["source_policy"] == "pgrr", list(columns)]
    paired = reference.merge(
        treatment,
        on="pair_id",
        validate="one_to_one",
        suffixes=("_reference", "_treatment"),
    )
    if len(paired) != expected_conditions:
        raise ReportInputError("joint-success efficiency pairing lost Base--PGRR conditions")
    joint_success = paired.loc[
        paired["_valid_reference"]
        & paired["_valid_treatment"]
        & paired["outcome_reference"].eq("GOAL_REACHED")
        & paired["outcome_treatment"].eq("GOAL_REACHED")
    ]

    metric_records: dict[str, dict[str, Any]] = {}
    for key, column, label, unit in (
        ("duration", "episode_duration_s", "共同到达 episode 时长", "s"),
        ("path_length", "path_length_m", "共同到达路径长度", "m"),
    ):
        json_key = (
            "successful_episode_duration_s" if key == "duration" else "successful_path_length_m"
        )
        analysis = continuous.get(json_key)
        if not isinstance(analysis, Mapping):
            raise ReportInputError(f"pairwise statistics omit base/{json_key}")
        if analysis.get("population") != "joint_success":
            raise ReportInputError(f"base/{json_key} must use the joint_success population")
        reference_values = pd.to_numeric(
            joint_success[f"{column}_reference"], errors="coerce"
        ).to_numpy(dtype=float)
        treatment_values = pd.to_numeric(
            joint_success[f"{column}_treatment"], errors="coerce"
        ).to_numpy(dtype=float)
        finite = np.isfinite(reference_values) & np.isfinite(treatment_values)
        reference_values = reference_values[finite]
        treatment_values = treatment_values[finite]
        pair_count = int(reference_values.size)
        if _integer(analysis.get("pair_count"), field=f"base/{json_key}.pair_count") != pair_count:
            raise ReportInputError(f"statistics pair count disagrees for base/{json_key}")
        if pair_count == 0:
            if analysis.get("status") != "insufficient_finite_pairs":
                raise ReportInputError(
                    f"statistics base/{json_key} must declare insufficient finite pairs"
                )
            metric_records[key] = {
                "json_metric": json_key,
                "label": label,
                "unit": unit,
                "population": "joint_success",
                "pair_count": 0,
                "available": False,
            }
            continue
        if analysis.get("status") != "ok":
            raise ReportInputError(f"statistics base/{json_key} is not successful")
        reference_mean = _finite(
            analysis.get("reference_mean"), field=f"base/{json_key}.reference_mean"
        )
        treatment_mean = _finite(
            analysis.get("treatment_mean"), field=f"base/{json_key}.treatment_mean"
        )
        for field, observed, expected in (
            ("reference_mean", reference_mean, float(np.mean(reference_values))),
            ("treatment_mean", treatment_mean, float(np.mean(treatment_values))),
        ):
            if not math.isclose(observed, expected, rel_tol=1.0e-12, abs_tol=1.0e-12):
                raise ReportInputError(f"statistics {field} disagrees for base/{json_key}")
        interval = analysis.get("difference_treatment_minus_reference")
        if not isinstance(interval, Mapping):
            raise ReportInputError(f"statistics omit paired difference for base/{json_key}")
        difference = _finite(interval.get("estimate"), field=f"base/{json_key}.estimate")
        ci_lower = _finite(interval.get("lower"), field=f"base/{json_key}.lower")
        ci_upper = _finite(interval.get("upper"), field=f"base/{json_key}.upper")
        expected_difference = float(np.mean(treatment_values - reference_values))
        if not math.isclose(difference, expected_difference, rel_tol=1.0e-12, abs_tol=1.0e-12):
            raise ReportInputError(f"statistics paired difference disagrees for base/{json_key}")
        if not ci_lower <= difference <= ci_upper:
            raise ReportInputError(f"invalid paired interval for base/{json_key}")
        confidence = _probability(interval.get("confidence"), field=f"base/{json_key}.confidence")
        if not math.isclose(confidence, 0.95, abs_tol=1.0e-12):
            raise ReportInputError("joint-success efficiency must use 95% intervals")
        if (
            _integer(
                interval.get("bootstrap_samples"),
                field=f"base/{json_key}.bootstrap_samples",
            )
            != bootstrap_samples
        ):
            raise ReportInputError(
                f"statistics bootstrap sample count disagrees for base/{json_key}"
            )
        test = analysis.get("wilcoxon")
        if not isinstance(test, Mapping):
            raise ReportInputError(f"statistics omit Wilcoxon test for base/{json_key}")
        pvalue_raw = _probability(test.get("pvalue_raw"), field=f"base/{json_key}.raw p")
        pvalue_holm = _probability(test.get("pvalue_holm"), field=f"base/{json_key}.Holm p")
        nonzero_pairs = _integer(test.get("nonzero_pairs"), field=f"base/{json_key}.nonzero_pairs")
        expected_nonzero = int(np.count_nonzero(treatment_values - reference_values))
        if nonzero_pairs != expected_nonzero:
            raise ReportInputError(f"statistics nonzero-pair count disagrees for base/{json_key}")
        hypothesis = f"base::wilcoxon_{json_key}"
        global_row = global_evidence.get(hypothesis)
        if (
            global_row is None
            or global_row.get("comparator") != "base"
            or global_row.get("test") != f"wilcoxon_{json_key}"
            or not math.isclose(
                float(global_row["pvalue_raw"]), pvalue_raw, rel_tol=1.0e-12, abs_tol=1.0e-12
            )
            or not math.isclose(
                float(global_row["pvalue_holm_global"]),
                pvalue_holm,
                rel_tol=1.0e-12,
                abs_tol=1.0e-12,
            )
        ):
            raise ReportInputError(f"statistics global Holm row disagrees for {hypothesis}")
        metric_records[key] = {
            "json_metric": json_key,
            "label": label,
            "unit": unit,
            "population": "joint_success",
            "pair_count": pair_count,
            "available": True,
            "reference_mean": reference_mean,
            "treatment_mean": treatment_mean,
            "difference_pgrr_minus_base": difference,
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
            "confidence": confidence,
            "pvalue_raw": pvalue_raw,
            "pvalue_holm": pvalue_holm,
            "holm_scope": "all reported tests across every comparator versus PGRR",
        }

    pair_counts = {int(record["pair_count"]) for record in metric_records.values()}
    if len(pair_counts) != 1:
        raise ReportInputError("joint-success duration and path-length pair counts disagree")
    return {
        "reference_policy": "base",
        "treatment_policy": "pgrr",
        "population": "joint_success",
        "pair_count": pair_counts.pop(),
        "available": all(bool(record["available"]) for record in metric_records.values()),
        "metrics": metric_records,
    }


def _validate_validation_matched_evidence(
    payload: object,
    *,
    results: pd.DataFrame,
    results_sha256: str,
    stage: str,
) -> dict[str, Any]:
    """Cross-check a validation-only matched raw trace against its Parquet rows."""

    if stage != "validation":
        raise ReportInputError("schema-v1 matched telemetry is validation-only")

    if not isinstance(payload, dict):
        raise ReportInputError("matched evidence must be a JSON object")
    expected_header = {
        "schema_version": 1,
        "artifact_type": "matched_base_pgrr_raw_telemetry",
        "benchmark_id": BENCHMARK_ID,
        "stage": stage,
        "selection_rule": "doorway_bottleneck/medium/replicate-0; outcome-independent",
        "representation": "telemetry reconstruction; not a simulator camera screenshot",
    }
    for field, expected in expected_header.items():
        if payload.get(field) != expected:
            raise ReportInputError(f"matched evidence {field} does not equal {expected!r}")
    if payload.get("results_sha256") != results_sha256:
        raise ReportInputError("matched evidence is bound to a different results.parquet")
    selector = payload.get("selector")
    expected_selector = {"family": "doorway_bottleneck", "density": "medium", "replicate": 0}
    if selector != expected_selector:
        raise ReportInputError("matched evidence selector is not the preregistered condition")
    selected = results.loc[
        (results["family"].astype(str) == "doorway_bottleneck")
        & (results["density"].astype(str) == "medium")
        & (pd.to_numeric(results["replicate"], errors="coerce") == 0)
        & results["source_policy"].isin(("base", "pgrr"))
    ].copy()
    if len(selected) != 2 or selected["pair_id"].astype(str).nunique() != 1:
        raise ReportInputError(
            "fixed matched selector does not resolve one complete Base/PGRR pair"
        )
    pair_id = str(selected.iloc[0]["pair_id"])
    if payload.get("pair_id") != pair_id:
        raise ReportInputError("matched evidence pair_id disagrees with results")
    if payload.get("scenario_id") != str(selected.iloc[0]["scenario_id"]):
        raise ReportInputError("matched evidence scenario_id disagrees with results")
    if payload.get("scenario_sha256") != str(selected.iloc[0].get("scenario_sha256", "")):
        raise ReportInputError("matched evidence scenario SHA256 disagrees with results")
    evidence_seed = _integer(payload.get("seed"), field="matched evidence seed")
    if evidence_seed != int(selected.iloc[0]["seed"]):
        raise ReportInputError("matched evidence seed disagrees with results")
    runs = payload.get("runs")
    if not isinstance(runs, Mapping) or set(runs) != {"base", "pgrr"}:
        raise ReportInputError("matched evidence must contain exactly Base and PGRR traces")
    trace_fields = (
        "time_s",
        "robot_x_m",
        "robot_y_m",
        "distance_to_goal_m",
        "failure_score",
        "recovery_state",
        "recovery_action",
    )
    run_summary: dict[str, Any] = {}
    for method in ("base", "pgrr"):
        run = runs[method]
        if not isinstance(run, Mapping):
            raise ReportInputError(f"matched evidence run {method} must be an object")
        row = selected.loc[selected["source_policy"] == method].iloc[0]
        for field in ("episode_id", "outcome", "raw_sha256"):
            if str(run.get(field, "")) != str(row[field]):
                raise ReportInputError(f"matched evidence {method}/{field} disagrees with results")
        if Path(str(run.get("raw_file", ""))).name != f"{row['episode_id']}.jsonl":
            raise ReportInputError(f"matched evidence {method} raw filename is not episode-bound")
        trace = run.get("trace")
        if not isinstance(trace, Mapping) or set(trace) != set(trace_fields):
            raise ReportInputError(f"matched evidence {method} trace fields are incomplete")
        lengths = {len(values) if isinstance(values, list) else -1 for values in trace.values()}
        if len(lengths) != 1:
            raise ReportInputError(f"matched evidence {method} trace arrays differ in length")
        sample_count = lengths.pop()
        if not 2 <= sample_count <= 480:
            raise ReportInputError(f"matched evidence {method} sample count is invalid")
        if (
            _integer(
                run.get("sample_count_exported"), field=f"matched evidence {method} sample count"
            )
            != sample_count
        ):
            raise ReportInputError(f"matched evidence {method} sample count is inconsistent")
        numeric_fields = trace_fields[:5]
        for field in numeric_fields:
            for value in trace[field]:
                _finite(value, field=f"matched evidence {method}/{field}")
        times = [float(value) for value in trace["time_s"]]
        if any(right < left for left, right in pairwise(times)):
            raise ReportInputError(f"matched evidence {method} timestamps are not monotonic")
        if any(not str(value).strip() for value in trace["recovery_state"]):
            raise ReportInputError(f"matched evidence {method} contains an empty recovery state")
        run_summary[method] = {
            "episode_id": str(run["episode_id"]),
            "outcome": str(run["outcome"]),
            "raw_sha256": str(run["raw_sha256"]),
            "sample_count_exported": sample_count,
        }
    return {
        "pair_id": pair_id,
        "scenario_id": str(payload["scenario_id"]),
        "seed": int(payload["seed"]),
        "selection_rule": str(payload["selection_rule"]),
        "representation": str(payload["representation"]),
        "runs": run_summary,
    }


def _sha256_text(value: object, *, field: str) -> str:
    digest = str(value).strip().lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ReportInputError(f"matched evidence {field} must be a lowercase SHA256 digest")
    return digest


def _resolve_matched_media_artifact(
    declaration: object,
    *,
    evidence_path: Path,
    field: str,
    filename: str,
) -> tuple[Path, dict[str, str]]:
    """Resolve one fixed final-media PDF without permitting path escape."""

    if not isinstance(declaration, Mapping):
        raise ReportInputError(f"matched evidence artifact {field} must be an object")
    if declaration.get("filename") != filename:
        raise ReportInputError(
            f"matched evidence artifact {field} must use fixed filename {filename}"
        )
    if declaration.get("media_type") != "application/pdf":
        raise ReportInputError(f"matched evidence artifact {field} must be application/pdf")
    declared_path = Path(str(declaration.get("path", "")))
    if not str(declared_path) or declared_path.is_absolute() or declared_path.name != filename:
        raise ReportInputError(
            f"matched evidence artifact {field} must use a relative path ending in {filename}"
        )
    evidence_directory = evidence_path.parent.resolve()
    resolved = (evidence_directory / declared_path).resolve()
    if not _inside(resolved, evidence_directory):
        raise ReportInputError(f"matched evidence artifact {field} escapes the approved directory")
    if not resolved.is_file():
        raise ReportInputError(f"matched evidence artifact {field} is missing: {declared_path}")
    if resolved.read_bytes()[:4] != b"%PDF":
        raise ReportInputError(f"matched evidence artifact {field} is not a PDF")
    declared_sha = _sha256_text(declaration.get("sha256"), field=f"artifacts.{field}.sha256")
    if _sha256(resolved) != declared_sha:
        raise ReportInputError(f"matched evidence artifact {field} SHA256 disagrees")
    return resolved, {
        "path": declared_path.as_posix(),
        "filename": filename,
        "sha256": declared_sha,
        "media_type": "application/pdf",
    }


def _validate_test_matched_evidence(
    payload: object,
    *,
    results: pd.DataFrame,
    results_sha256: str,
    evidence_path: Path,
) -> dict[str, Any]:
    """Cross-check locked-test media, provenance, and the selected same-pair rows."""

    if not isinstance(payload, dict):
        raise ReportInputError("matched evidence must be a JSON object")
    expected_header = {
        "schema_version": 2,
        "artifact_type": "matched_base_pgrr_test_media",
        "benchmark_id": BENCHMARK_ID,
        "stage": "test",
        "selection_rule": MATCHED_TEST_SELECTION_RULE,
        "representation": "telemetry reconstruction; not a simulator camera screenshot",
        "results_file": "results.parquet",
    }
    for field, expected in expected_header.items():
        if payload.get(field) != expected:
            raise ReportInputError(f"matched evidence {field} does not equal {expected!r}")
    if payload.get("results_sha256") != results_sha256:
        raise ReportInputError("matched evidence is bound to a different results.parquet")

    pair_id = str(payload.get("pair_id", "")).strip()
    selected = results.loc[
        (results["pair_id"].astype(str) == pair_id)
        & results["source_policy"].isin(("base", "pgrr"))
    ].copy()
    if len(selected) != 2 or set(selected["source_policy"].astype(str)) != {"base", "pgrr"}:
        raise ReportInputError("matched test evidence does not select one complete Base/PGRR pair")
    if "included_in_algorithm_metrics" in selected and not bool(
        selected["included_in_algorithm_metrics"].astype(bool).all()
    ):
        raise ReportInputError("matched test media must use two algorithm-valid episodes")

    first = selected.iloc[0]
    scalar_fields = ("scenario_id", "scenario_sha256", "family", "density", "seed")
    for field in scalar_fields:
        expected = int(first[field]) if field == "seed" else str(first[field])
        observed = (
            _integer(payload.get(field), field=f"matched evidence {field}")
            if field == "seed"
            else str(payload.get(field, ""))
        )
        if observed != expected:
            raise ReportInputError(f"matched evidence {field} disagrees with results")
    for field in scalar_fields:
        if selected[field].astype(str).nunique(dropna=False) != 1:
            raise ReportInputError(f"matched test pair differs across methods for {field}")

    if "project_commit" not in selected:
        raise ReportInputError("locked test results omit project_commit provenance")
    commits = selected["project_commit"].astype(str)
    if commits.nunique(dropna=False) != 1:
        raise ReportInputError("matched test pair differs across methods for project_commit")
    project_commit = str(payload.get("project_commit", ""))
    if (
        project_commit != str(commits.iloc[0])
        or len(project_commit) != 40
        or any(character not in "0123456789abcdef" for character in project_commit.lower())
    ):
        raise ReportInputError("matched evidence project_commit disagrees with results")

    required_result_hashes = ("raw_sha256", "metadata_sha256", "outcome_sha256")
    missing_hashes = [field for field in required_result_hashes if field not in selected]
    if missing_hashes:
        raise ReportInputError(f"locked test results omit matched provenance: {missing_hashes}")
    runs = payload.get("runs")
    if not isinstance(runs, Mapping) or set(runs) != {"base", "pgrr"}:
        raise ReportInputError("matched evidence must contain exactly Base and PGRR runs")
    run_summary: dict[str, Any] = {}
    for method in ("base", "pgrr"):
        run = runs[method]
        if not isinstance(run, Mapping):
            raise ReportInputError(f"matched evidence run {method} must be an object")
        row = selected.loc[selected["source_policy"] == method].iloc[0]
        for field in ("episode_id", "outcome"):
            if str(run.get(field, "")) != str(row[field]):
                raise ReportInputError(f"matched evidence {method}/{field} disagrees with results")
        if str(run.get("outcome")) not in OUTCOMES:
            raise ReportInputError(f"matched evidence {method} uses an excluded outcome")
        if Path(str(run.get("raw_file", ""))).name != f"{row['episode_id']}.jsonl":
            raise ReportInputError(f"matched evidence {method} raw filename is not episode-bound")
        hashes: dict[str, str] = {}
        for field in required_result_hashes:
            observed = _sha256_text(run.get(field), field=f"runs.{method}.{field}")
            expected = _sha256_text(row[field], field=f"results.{method}.{field}")
            if observed != expected:
                raise ReportInputError(f"matched evidence {method}/{field} disagrees with results")
            hashes[field] = observed
        sample_count = _integer(
            run.get("sample_count"), field=f"matched evidence {method} sample_count"
        )
        if sample_count < 2:
            raise ReportInputError(f"matched evidence {method} sample count is invalid")
        if "sample_count" in selected and not pd.isna(row["sample_count"]):
            if sample_count != _integer(
                row["sample_count"], field=f"results {method} sample_count"
            ):
                raise ReportInputError(
                    f"matched evidence {method} sample count disagrees with results"
                )
        run_summary[method] = {
            "episode_id": str(run["episode_id"]),
            "outcome": str(run["outcome"]),
            "raw_sha256": hashes["raw_sha256"],
            "metadata_sha256": hashes["metadata_sha256"],
            "outcome_sha256": hashes["outcome_sha256"],
            "sample_count": sample_count,
        }

    declarations = payload.get("artifacts")
    if not isinstance(declarations, Mapping) or set(declarations) != {
        "trajectory",
        "recovery_timeline",
    }:
        raise ReportInputError("matched test evidence must contain both fixed media artifacts")
    _, trajectory = _resolve_matched_media_artifact(
        declarations["trajectory"],
        evidence_path=evidence_path,
        field="trajectory",
        filename=MATCHED_TRAJECTORY_FILENAME,
    )
    _, timeline = _resolve_matched_media_artifact(
        declarations["recovery_timeline"],
        evidence_path=evidence_path,
        field="recovery_timeline",
        filename=MATCHED_TIMELINE_FILENAME,
    )
    return {
        "artifact_type": "matched_base_pgrr_test_media",
        "pair_id": pair_id,
        "scenario_id": str(payload["scenario_id"]),
        "scenario_sha256": str(payload["scenario_sha256"]),
        "family": str(payload["family"]),
        "density": str(payload["density"]),
        "seed": int(payload["seed"]),
        "project_commit": project_commit,
        "selection_rule": str(payload["selection_rule"]),
        "representation": str(payload["representation"]),
        "runs": run_summary,
        "artifacts": {"trajectory": trajectory, "recovery_timeline": timeline},
    }


def validate_matched_evidence(
    payload: object,
    *,
    results: pd.DataFrame,
    results_sha256: str,
    stage: str,
    evidence_path: Path | None = None,
) -> dict[str, Any]:
    """Dispatch to the validation trace or the stricter fixed test-media schema."""

    if stage == "validation":
        return _validate_validation_matched_evidence(
            payload,
            results=results,
            results_sha256=results_sha256,
            stage=stage,
        )
    if stage == "test":
        if evidence_path is None:
            raise ReportInputError("test matched evidence validation requires its sidecar path")
        return _validate_test_matched_evidence(
            payload,
            results=results,
            results_sha256=results_sha256,
            evidence_path=evidence_path,
        )
    raise ReportInputError(f"stage {stage!r} cannot consume matched evidence")


def _rate(frame: pd.DataFrame, outcome: str) -> float:
    if frame.empty:
        return math.nan
    return float((frame["outcome"] == outcome).mean())


def _method_summary(results: pd.DataFrame) -> list[dict[str, Any]]:
    valid = _valid_rows(results)
    rows: list[dict[str, Any]] = []
    for method in METHODS:
        group = valid.loc[valid["source_policy"] == method]
        trigger_total = float(group["recovery_trigger_count"].sum())
        recovery_total = float(group["recovery_success_count"].sum())
        rows.append(
            {
                "method": method,
                "label": METHOD_LABELS[method],
                "valid_episodes": len(group),
                "goal_rate": _rate(group, "GOAL_REACHED"),
                "collision_rate": _rate(group, "COLLISION"),
                "timeout_rate": _rate(group, "TIMEOUT"),
                "planner_failure_rate": _rate(group, "PLANNER_FAILURE"),
                "median_navigation_time_s": float(group["navigation_time_s"].median()),
                "median_min_human_distance_m": float(group["min_human_distance_m"].median()),
                "mean_recovery_triggers": float(group["recovery_trigger_count"].mean()),
                "aggregate_recovery_success_rate": (
                    recovery_total / trigger_total if trigger_total > 0.0 else None
                ),
                "mean_recovery_duration_s": float(group["recovery_duration_s"].mean()),
                "mean_intervention_ratio": float(group["intervention_ratio"].mean()),
            }
        )
    return rows


def _base_pgrr_planner_failure(results: pd.DataFrame) -> dict[str, Any]:
    """Return the declared descriptive-only planner-failure comparison."""

    valid = _valid_rows(results)
    records: dict[str, dict[str, Any]] = {}
    for method in ("base", "pgrr"):
        group = valid.loc[valid["source_policy"] == method]
        denominator = len(group)
        if denominator <= 0:
            raise ReportInputError(f"planner-failure rate has no valid {method} episodes")
        count = int(group["outcome"].eq("PLANNER_FAILURE").sum())
        records[method] = {
            "valid_episode_count": denominator,
            "count": count,
            "rate": count / denominator,
        }
    return {
        "endpoint": "PLANNER_FAILURE",
        "analysis": "descriptive_marginal_rate_difference",
        "preregistered_inferential_endpoint": False,
        "post_hoc_significance_test": False,
        "base": records["base"],
        "pgrr": records["pgrr"],
        "rate_difference_pgrr_minus_base": (
            float(records["pgrr"]["rate"]) - float(records["base"]["rate"])
        ),
    }


def _density_summary(results: pd.DataFrame) -> list[dict[str, Any]]:
    valid = _valid_rows(results)
    rows: list[dict[str, Any]] = []
    for density in DENSITIES:
        for method in METHODS:
            group = valid.loc[(valid["density"] == density) & (valid["source_policy"] == method)]
            rows.append(
                {
                    "density": density,
                    "method": method,
                    "valid_episodes": len(group),
                    "goal_rate": _rate(group, "GOAL_REACHED"),
                }
            )
    return rows


def _family_summary(results: pd.DataFrame) -> list[dict[str, Any]]:
    valid = _valid_rows(results)
    rows: list[dict[str, Any]] = []
    for family in FAMILIES:
        for method in METHODS:
            group = valid.loc[(valid["family"] == family) & (valid["source_policy"] == method)]
            rows.append(
                {
                    "family": family,
                    "method": method,
                    "goals": int((group["outcome"] == "GOAL_REACHED").sum()),
                    "valid_episodes": len(group),
                    "goal_rate": _rate(group, "GOAL_REACHED"),
                }
            )
    return rows


def _paired_effects(results: pd.DataFrame) -> dict[str, float]:
    valid = _valid_rows(results)
    pivot = valid.pivot(index="pair_id", columns="source_policy", values="outcome")
    complete = pivot.dropna(subset=["base", "pgrr"])
    effects: dict[str, float] = {"pair_count": float(len(complete))}
    for outcome, key in (
        ("GOAL_REACHED", "goal_difference"),
        ("COLLISION", "collision_difference"),
        ("TIMEOUT", "timeout_difference"),
    ):
        effects[key] = float(
            (complete["pgrr"] == outcome).astype(float).mean()
            - (complete["base"] == outcome).astype(float).mean()
        )
    return effects


def _configure_plotting() -> None:
    font_family = "DejaVu Sans"
    for candidate in (
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"),
    ):
        if candidate.is_file():
            font_manager.fontManager.addfont(candidate)
            font_family = font_manager.FontProperties(fname=candidate).get_name()
            break
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [font_family, "Noto Sans CJK SC", "DejaVu Sans"],
            "font.size": 9.0,
            "axes.edgecolor": "#59636B",
            "axes.labelcolor": "#1B1F23",
            "text.color": "#1B1F23",
            "xtick.color": "#1B1F23",
            "ytick.color": "#1B1F23",
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "pdf.fonttype": 42,
        }
    )


def _save_figure(figure: plt.Figure, stem: Path) -> None:
    for suffix, dpi in ((".pdf", None), (".png", 180)):
        kwargs: dict[str, Any] = {"bbox_inches": "tight"}
        if dpi is not None:
            kwargs["dpi"] = dpi
        figure.savefig(stem.with_suffix(suffix), **kwargs)
    plt.close(figure)


def _matched_run_figure(payload: Mapping[str, Any], output_dir: Path) -> None:
    """Render hash-verified raw telemetry without implying camera imagery."""

    runs = payload["runs"]
    figure, axes = plt.subplots(2, 2, figsize=(10.2, 6.6), constrained_layout=True)
    for method in ("base", "pgrr"):
        run = runs[method]
        trace = run["trace"]
        label = f"{METHOD_LABELS[method]} · {run['outcome']}"
        color = METHOD_COLORS[method]
        axes[0, 0].plot(
            trace["robot_x_m"], trace["robot_y_m"], color=color, linewidth=1.8, label=label
        )
        axes[0, 0].scatter(
            trace["robot_x_m"][0], trace["robot_y_m"][0], color=color, marker="o", s=32
        )
        axes[0, 0].scatter(
            trace["robot_x_m"][-1], trace["robot_y_m"][-1], color=color, marker="X", s=48
        )
        axes[0, 1].plot(
            trace["time_s"],
            trace["distance_to_goal_m"],
            color=color,
            linewidth=1.7,
            label=label,
        )
        axes[1, 0].plot(
            trace["time_s"], trace["failure_score"], color=color, linewidth=1.6, label=label
        )

    pgrr_trace = runs["pgrr"]["trace"]
    state_order = list(dict.fromkeys(str(value) for value in pgrr_trace["recovery_state"]))
    state_to_index = {state: index for index, state in enumerate(state_order)}
    state_values = [state_to_index[str(value)] for value in pgrr_trace["recovery_state"]]
    axes[1, 1].step(
        pgrr_trace["time_s"],
        state_values,
        where="post",
        color=METHOD_COLORS["pgrr"],
        linewidth=1.7,
    )
    axes[1, 1].set_yticks(np.arange(len(state_order)), state_order)

    axes[0, 0].set_title("机器人平面轨迹（○ 起点，× 终点）")
    axes[0, 0].set_xlabel("x（m）")
    axes[0, 0].set_ylabel("y（m）")
    axes[0, 0].axis("equal")
    axes[0, 1].set_title("原始目标距离时间线")
    axes[0, 1].set_xlabel("仿真时间（s）")
    axes[0, 1].set_ylabel("目标距离（m）")
    axes[1, 0].set_title("可观测失败分数时间线")
    axes[1, 0].set_xlabel("仿真时间（s）")
    axes[1, 0].set_ylabel("failure score")
    axes[1, 1].set_title("PGRR 恢复状态事件线")
    axes[1, 1].set_xlabel("仿真时间（s）")
    axes[1, 1].set_ylabel("记录状态 ID / 名称")
    for axis in axes.flat:
        axis.grid(color="#D7DDE1", linewidth=0.6, alpha=0.8)
        axis.set_axisbelow(True)
    axes[0, 0].legend(frameon=False, fontsize=8)
    axes[0, 1].legend(frameon=False, fontsize=8)
    axes[1, 0].legend(frameon=False, fontsize=8)
    figure.suptitle(
        "预注册 matched pair：doorway bottleneck / medium / r00\n"
        "来自 SHA256 校验的 JSONL → 审计 sidecar；遥测重建，不是相机截图",
        fontsize=11.0,
        fontweight="bold",
    )
    _save_figure(figure, output_dir / "result_matched_run_evidence")


def _copy_fixed_test_media(
    summary: Mapping[str, Any], *, evidence_path: Path, output_dir: Path
) -> None:
    """Copy only SHA-validated locked-test media into stable report asset names."""

    artifacts = summary["artifacts"]
    assert isinstance(artifacts, Mapping)
    targets = {
        "trajectory": output_dir / "result_matched_trajectory.pdf",
        "recovery_timeline": output_dir / "result_matched_recovery_timeline.pdf",
    }
    fixed_names = {
        "trajectory": MATCHED_TRAJECTORY_FILENAME,
        "recovery_timeline": MATCHED_TIMELINE_FILENAME,
    }
    for field, destination in targets.items():
        declaration = artifacts[field]
        assert isinstance(declaration, Mapping)
        source, _ = _resolve_matched_media_artifact(
            declaration,
            evidence_path=evidence_path,
            field=field,
            filename=fixed_names[field],
        )
        shutil.copyfile(source, destination)
        if _sha256(destination) != declaration["sha256"]:
            raise ReportInputError(f"copied matched evidence artifact {field} changed SHA256")


def _outcome_figure(results: pd.DataFrame, output_dir: Path) -> None:
    valid = _valid_rows(results)
    figure, axis = plt.subplots(figsize=(7.4, 3.7), constrained_layout=True)
    bottoms = np.zeros(len(METHODS), dtype=float)
    for outcome in OUTCOMES:
        rates = np.array(
            [_rate(valid.loc[valid["source_policy"] == method], outcome) for method in METHODS]
        )
        axis.bar(
            np.arange(len(METHODS)),
            rates * 100.0,
            bottom=bottoms,
            color=OUTCOME_COLORS[outcome],
            label=outcome.replace("_", " ").title(),
            edgecolor="white",
            linewidth=0.7,
        )
        bottoms += rates * 100.0
    axis.set_xticks(np.arange(len(METHODS)), [METHOD_LABELS[m] for m in METHODS])
    axis.set_ylabel("终止结果占比（%）")
    axis.set_ylim(0.0, 100.0)
    axis.grid(axis="y", color="#D7DDE1", linewidth=0.6, alpha=0.8)
    axis.set_axisbelow(True)
    axis.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.16), frameon=False)
    _save_figure(figure, output_dir / "result_outcomes")


def _density_figure(results: pd.DataFrame, output_dir: Path) -> None:
    valid = _valid_rows(results)
    figure, axis = plt.subplots(figsize=(7.4, 3.7), constrained_layout=True)
    x = np.arange(len(DENSITIES), dtype=float)
    width = 0.15
    for index, method in enumerate(METHODS):
        values = [
            _rate(
                valid.loc[(valid["source_policy"] == method) & (valid["density"] == density)],
                "GOAL_REACHED",
            )
            * 100.0
            for density in DENSITIES
        ]
        axis.bar(
            x + (index - 2) * width,
            values,
            width=width,
            color=METHOD_COLORS[method],
            label=METHOD_LABELS[method],
        )
    axis.set_xticks(x, [density.title() for density in DENSITIES])
    axis.set_ylabel("目标到达率（%）")
    axis.set_ylim(0.0, 100.0)
    axis.grid(axis="y", color="#D7DDE1", linewidth=0.6, alpha=0.8)
    axis.set_axisbelow(True)
    axis.legend(ncol=5, loc="upper center", bbox_to_anchor=(0.5, 1.16), frameon=False)
    _save_figure(figure, output_dir / "result_density")


def _family_figure(results: pd.DataFrame, output_dir: Path) -> None:
    valid = _valid_rows(results)
    matrix = np.full((len(FAMILIES), len(METHODS)), np.nan, dtype=float)
    for row, family in enumerate(FAMILIES):
        for column, method in enumerate(METHODS):
            group = valid.loc[(valid["family"] == family) & (valid["source_policy"] == method)]
            matrix[row, column] = _rate(group, "GOAL_REACHED") * 100.0
    figure, axis = plt.subplots(figsize=(7.4, 4.8), constrained_layout=True)
    image = axis.imshow(matrix, vmin=0.0, vmax=100.0, cmap="Blues", aspect="auto")
    axis.set_xticks(np.arange(len(METHODS)), [METHOD_LABELS[m] for m in METHODS])
    axis.set_yticks(
        np.arange(len(FAMILIES)),
        [family.replace("_", " ").title() for family in FAMILIES],
    )
    for row in range(len(FAMILIES)):
        for column in range(len(METHODS)):
            value = matrix[row, column]
            color = "white" if value >= 58.0 else "#1B1F23"
            axis.text(column, row, f"{value:.0f}%", ha="center", va="center", color=color)
    colorbar = figure.colorbar(image, ax=axis, fraction=0.025, pad=0.02)
    colorbar.set_label("目标到达率（%）")
    _save_figure(figure, output_dir / "result_family")


def _safety_efficiency_figure(results: pd.DataFrame, output_dir: Path) -> None:
    valid = _valid_rows(results)
    figure, axis = plt.subplots(figsize=(7.4, 3.9), constrained_layout=True)
    for method in METHODS:
        group = valid.loc[valid["source_policy"] == method]
        successful = group.loc[group["outcome"] == "GOAL_REACHED"]
        x = float(successful["navigation_time_s"].median()) if not successful.empty else math.nan
        y = float(group["min_human_distance_m"].median())
        if math.isfinite(x) and math.isfinite(y):
            axis.scatter(x, y, s=72, color=METHOD_COLORS[method], label=METHOD_LABELS[method])
            axis.annotate(METHOD_LABELS[method], (x, y), xytext=(5, 5), textcoords="offset points")
    axis.set_xlabel("成功 episode 的中位导航时间（s）")
    axis.set_ylabel("全部有效 episode 的中位最小人距（m）")
    axis.grid(color="#D7DDE1", linewidth=0.6, alpha=0.8)
    axis.set_axisbelow(True)
    _save_figure(figure, output_dir / "result_safety_efficiency")


def _joint_success_efficiency_figure(efficiency: Mapping[str, Any], output_dir: Path) -> None:
    """Render Base--PGRR paired efficiency conditional on both methods succeeding."""

    metrics = efficiency["metrics"]
    assert isinstance(metrics, Mapping)
    figure, axes = plt.subplots(1, 2, figsize=(10.8, 4.0), constrained_layout=True)
    for axis, key, title in zip(
        axes,
        ("duration", "path_length"),
        ("共同到达 episode 时长", "共同到达路径长度"),
        strict=True,
    ):
        record = metrics[key]
        assert isinstance(record, Mapping)
        axis.axvline(0.0, color="#59636B", linewidth=0.9, linestyle="--")
        if bool(record["available"]):
            estimate = float(record["difference_pgrr_minus_base"])
            lower = float(record["ci_lower"])
            upper = float(record["ci_upper"])
            axis.errorbar(
                [estimate],
                [0.0],
                xerr=[[estimate - lower], [upper - estimate]],
                fmt="o",
                color=METHOD_COLORS["pgrr"],
                capsize=4,
                linewidth=1.7,
            )
            axis.set_yticks([])
            axis.set_xlabel(f"PGRR - DWB（{record['unit']}）")
            axis.text(
                0.5,
                0.88,
                f"n={record['pair_count']}；95% CI；"
                f"p_H={_format_pvalue(float(record['pvalue_holm']))}",
                transform=axis.transAxes,
                ha="center",
                va="center",
                fontsize=8.5,
            )
        else:
            axis.set_axis_off()
            axis.text(
                0.5,
                0.5,
                "无有限的共同到达 pair；不可估计",
                transform=axis.transAxes,
                ha="center",
                va="center",
            )
        axis.set_title(title, fontweight="bold")
        axis.grid(axis="x", color="#D7DDE1", linewidth=0.6, alpha=0.8)
    figure.suptitle(
        "Base--PGRR joint-success 配对效率（失败终局仍在主结果中）",
        fontsize=11.0,
        fontweight="bold",
    )
    _save_figure(figure, output_dir / "result_joint_success_efficiency")


def _format_pvalue(value: float) -> str:
    if value < 0.001:
        return "<0.001"
    return f"{value:.3f}"


def _paired_effect_figure(records: Sequence[Mapping[str, Any]], output_dir: Path) -> None:
    """Render all twelve preregistered binary comparisons as a compact forest plot."""

    by_key = {(str(record["endpoint"]), str(record["comparator"])): record for record in records}
    figure, axes = plt.subplots(1, 3, figsize=(11.2, 4.7), sharey=True, constrained_layout=True)
    y = np.arange(len(COMPARATORS), dtype=float)
    for axis, (endpoint_key, _outcome, label, color, direction) in zip(
        axes, ENDPOINTS, strict=True
    ):
        endpoint_records = [by_key[(endpoint_key, comparator)] for comparator in COMPARATORS]
        estimates = np.asarray([100.0 * float(row["difference"]) for row in endpoint_records])
        lower = np.asarray([100.0 * float(row["ci_lower"]) for row in endpoint_records])
        upper = np.asarray([100.0 * float(row["ci_upper"]) for row in endpoint_records])
        axis.errorbar(
            estimates,
            y,
            xerr=np.vstack((estimates - lower, upper - estimates)),
            fmt="o",
            markersize=5.5,
            capsize=3.0,
            color=color,
            ecolor=color,
            linewidth=1.4,
        )
        axis.axvline(0.0, color="#59636B", linewidth=0.9, linestyle="--")
        axis.set_xlim(-100.0, 100.0)
        axis.set_xticks((-100.0, -50.0, 0.0, 50.0, 100.0))
        axis.set_title(f"{label}｜{direction}", fontsize=10.5, fontweight="bold")
        axis.set_xlabel("PGRR − baseline（百分点）")
        axis.set_yticks(y, [METHOD_LABELS[method] for method in COMPARATORS])
        axis.invert_yaxis()
        axis.grid(axis="x", color="#D7DDE1", linewidth=0.6, alpha=0.8)
        axis.set_axisbelow(True)
        for row_index, row in enumerate(endpoint_records):
            annotation = (
                f"p$_H$={_format_pvalue(float(row['pvalue_holm']))}\n"
                f"OR$_H$={float(row['matched_odds_ratio_haldane']):.2f}"
            )
            axis.text(
                0.98,
                row_index,
                annotation,
                transform=axis.get_yaxis_transform(),
                ha="right",
                va="center",
                fontsize=7.0,
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.84, "pad": 0.6},
            )
    figure.suptitle(
        "PGRR 相对四个 baseline 的配对差与 95% bootstrap CI\n"
        "p$_H$：全局 Holm 校正；OR$_H$：Haldane 校正的 matched odds ratio",
        fontsize=11.0,
        fontweight="bold",
    )
    _save_figure(figure, output_dir / "result_paired_effects")


def _result_table(summary: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\small",
        r"\caption{五种方法的完整终止结果。所有百分比以有效 episode 为分母。}",
        r"\begin{tabular}{lrrrrr}",
        r"\toprule",
        r"方法 & 有效数 & 到达 & 碰撞 & 超时 & 规划失败 \\",
        r"\midrule",
    ]
    for row in summary:
        lines.append(
            "{} & {} & {:.1f}\\% & {:.1f}\\% & {:.1f}\\% & {:.1f}\\% \\\\".format(
                _tex_escape(row["label"]),
                row["valid_episodes"],
                100.0 * float(row["goal_rate"]),
                100.0 * float(row["collision_rate"]),
                100.0 * float(row["timeout_rate"]),
                100.0 * float(row["planner_failure_rate"]),
            )
        )
    lines.extend((r"\bottomrule", r"\end{tabular}", r"\end{table}"))
    return "\n".join(lines) + "\n"


def _paired_statistics_table(records: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\scriptsize",
        r"\caption{PGRR 相对四个 baseline 的预注册二元端点配对统计。"
        r"差值为 PGRR--baseline 的百分点差；区间为配对 bootstrap 95\% CI；"
        r"$p_H$ 是所有比较与指标统一 Holm 校正后的精确 McNemar $p$ 值；"
        r"$\mathrm{OR}_H$ 是 Haldane 校正的 matched odds ratio。}",
        r"\begin{tabular}{llrrrr}",
        r"\toprule",
        r"Baseline & 端点 & 有效对数 & 差值 [95\% CI] & $p_H$ & $\mathrm{OR}_H$ \\",
        r"\midrule",
    ]
    previous = None
    for record in records:
        comparator = str(record["comparator"])
        if previous is not None and comparator != previous:
            lines.append(r"\addlinespace")
        lines.append(
            "{} & {} & {} & {:+.1f} [{:+.1f}, {:+.1f}] & {} & {:.2f} \\\\".format(
                _tex_escape(record["comparator_label"]),
                _tex_escape(record["endpoint_label"]),
                int(record["pair_count"]),
                100.0 * float(record["difference"]),
                100.0 * float(record["ci_lower"]),
                100.0 * float(record["ci_upper"]),
                _format_pvalue(float(record["pvalue_holm"])),
                float(record["matched_odds_ratio_haldane"]),
            )
        )
        previous = comparator
    lines.extend((r"\bottomrule", r"\end{tabular}", r"\end{table}"))
    return "\n".join(lines) + "\n"


def _pending_macros() -> str:
    return r"""% Generated by scripts/report/build_report_assets.py --stage pending.
\newif\ifReportResultsAvailable
\ReportResultsAvailablefalse
\newif\ifReportFixedTestMediaAvailable
\ReportFixedTestMediaAvailablefalse
\newif\ifReportJointSuccessEfficiencyAvailable
\ReportJointSuccessEfficiencyAvailablefalse
\newcommand{\ReportStageKey}{pending}
\newcommand{\ReportStageLabel}{验证执行中：结果尚未锁定}
\newcommand{\ReportStageNotice}{本报告当前只展示方法、系统和预注册实验协议。%
结果页明确保持待定，不读取历史、pilot、calibration 或运行中的验证输出。}
\newcommand{\ReportConditionCount}{--}
\newcommand{\ReportEpisodeCount}{--}
\newcommand{\ReportValidEpisodeCount}{--}
\newcommand{\ReportExcludedEpisodeCount}{--}
\newcommand{\ReportBaseGoalRate}{--}
\newcommand{\ReportPGRRGoalRate}{--}
\newcommand{\ReportGoalDifference}{--}
\newcommand{\ReportBasePlannerFailureRate}{--}
\newcommand{\ReportPGRRPlannerFailureRate}{--}
\newcommand{\ReportPlannerFailureDifference}{--}
\newcommand{\ReportJointSuccessPairCount}{--}
\newcommand{\ReportJointSuccessDurationDifference}{--}
\newcommand{\ReportJointSuccessDurationHolmP}{--}
\newcommand{\ReportJointSuccessPathDifference}{--}
\newcommand{\ReportJointSuccessPathHolmP}{--}
\newcommand{\ReportStatisticsSha}{--}
"""


def _result_macros(data: Mapping[str, Any]) -> str:
    summary = {row["method"]: row for row in data["method_summary"]}
    base = summary["base"]
    pgrr = summary["pgrr"]
    stage_label = "锁定测试集结果" if data["stage"] == "test" else "验证集快照：非最终测试结论"
    notice = (
        "数值来自锁定 moderate-v6 test 结果。"
        if data["stage"] == "test"
        else "数值仅用于验证阶段汇报，不得表述为最终测试结论。"
    )
    goal_difference = 100.0 * float(data["paired_effects"]["goal_difference"])
    planner_failure = data["base_pgrr_planner_failure"]
    efficiency = data["base_pgrr_joint_success_efficiency"]
    efficiency_metrics = efficiency["metrics"]
    duration = efficiency_metrics["duration"]
    path_length = efficiency_metrics["path_length"]
    efficiency_available = bool(efficiency["available"])

    def interval_macro(record: Mapping[str, Any]) -> str:
        if not bool(record["available"]):
            return "--"
        return (
            r"\ensuremath{"
            f"{float(record['difference_pgrr_minus_base']):+.3f}"
            rf"\,[{float(record['ci_lower']):+.3f},\,{float(record['ci_upper']):+.3f}]"
            rf"\,\mathrm{{{record['unit']}}}"
            "}"
        )

    def pvalue_macro(record: Mapping[str, Any]) -> str:
        if not bool(record["available"]):
            return "--"
        value = float(record["pvalue_holm"])
        return r"\ensuremath{<0.001}" if value < 0.001 else rf"\ensuremath{{={value:.3f}}}"

    fixed_test_media = (
        r"\ReportFixedTestMediaAvailabletrue"
        if data["stage"] == "test"
        else r"\ReportFixedTestMediaAvailablefalse"
    )
    return "\n".join(
        (
            "% Generated from a policy-approved results.parquet.",
            r"\newif\ifReportResultsAvailable",
            r"\ReportResultsAvailabletrue",
            r"\newif\ifReportFixedTestMediaAvailable",
            fixed_test_media,
            r"\newif\ifReportJointSuccessEfficiencyAvailable",
            (
                r"\ReportJointSuccessEfficiencyAvailabletrue"
                if efficiency_available
                else r"\ReportJointSuccessEfficiencyAvailablefalse"
            ),
            rf"\newcommand{{\ReportStageKey}}{{{_tex_escape(data['stage'])}}}",
            rf"\newcommand{{\ReportStageLabel}}{{{_tex_escape(stage_label)}}}",
            rf"\newcommand{{\ReportStageNotice}}{{{_tex_escape(notice)}}}",
            rf"\newcommand{{\ReportConditionCount}}{{{data['condition_count']}}}",
            rf"\newcommand{{\ReportEpisodeCount}}{{{data['episode_count']}}}",
            rf"\newcommand{{\ReportValidEpisodeCount}}{{{data['valid_episode_count']}}}",
            rf"\newcommand{{\ReportExcludedEpisodeCount}}{{{data['excluded_episode_count']}}}",
            rf"\newcommand{{\ReportBaseGoalRate}}{{{100.0 * float(base['goal_rate']):.1f}\%}}",
            rf"\newcommand{{\ReportPGRRGoalRate}}{{{100.0 * float(pgrr['goal_rate']):.1f}\%}}",
            rf"\newcommand{{\ReportGoalDifference}}{{{goal_difference:+.1f}个百分点}}",
            rf"\newcommand{{\ReportBasePlannerFailureRate}}"
            rf"{{{100.0 * float(planner_failure['base']['rate']):.1f}\%}}",
            rf"\newcommand{{\ReportPGRRPlannerFailureRate}}"
            rf"{{{100.0 * float(planner_failure['pgrr']['rate']):.1f}\%}}",
            rf"\newcommand{{\ReportPlannerFailureDifference}}"
            "{"
            f"{100.0 * float(planner_failure['rate_difference_pgrr_minus_base']):+.1f}"
            "个百分点}",
            rf"\newcommand{{\ReportJointSuccessPairCount}}{{{efficiency['pair_count']}}}",
            rf"\newcommand{{\ReportJointSuccessDurationDifference}}"
            rf"{{{interval_macro(duration)}}}",
            rf"\newcommand{{\ReportJointSuccessDurationHolmP}}"
            rf"{{{pvalue_macro(duration)}}}",
            rf"\newcommand{{\ReportJointSuccessPathDifference}}"
            rf"{{{interval_macro(path_length)}}}",
            rf"\newcommand{{\ReportJointSuccessPathHolmP}}"
            rf"{{{pvalue_macro(path_length)}}}",
            rf"\newcommand{{\ReportStatisticsSha}}{{{_tex_escape(data['statistics_sha256'][:12])}}}",
            "",
        )
    )


def build_report_assets(
    *,
    stage: str,
    results_path: Path | None,
    output_dir: Path,
    statistics_path: Path | None = None,
    matched_evidence_path: Path | None = None,
    project_root: Path = PROJECT_ROOT,
    expected_conditions: int | None = None,
    require_runtime_capture: bool = False,
) -> dict[str, Any]:
    """Build deterministic report inputs and return their machine-readable data."""

    if stage not in {"pending", "validation", "test"}:
        raise ReportInputError("stage must be one of: pending, validation, test")
    runtime_payload = (
        validate_runtime_capture(project_root)
        if require_runtime_capture or stage == "test"
        else None
    )
    runtime_summary = (
        _runtime_capture_summary(runtime_payload, project_root=project_root)
        if runtime_payload is not None
        else {
            "available": False,
            "representation": "real Gazebo GUI screenshot from a frozen validation demo",
            "not_locked_statistical_episode": True,
        }
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    if stage == "pending":
        if (
            results_path is not None
            or statistics_path is not None
            or matched_evidence_path is not None
        ):
            raise ReportInputError(
                "pending stage must not receive or inspect result/statistics/evidence files"
            )
        data: dict[str, Any] = {
            "schema_version": 3,
            "stage": "pending",
            "results_available": False,
            "notice": "Validation is running; no numerical result is approved for reporting.",
            "public_name": PUBLIC_NAME,
            "benchmark_id": BENCHMARK_ID,
            "runtime_capture": runtime_summary,
            "matched_run_evidence": {
                "available": False,
                "selection_rule": ("doorway_bottleneck/medium/replicate-0; outcome-independent"),
                "representation": "telemetry reconstruction; not a simulator camera screenshot",
            },
            "author_alias": "Charles Chen",
        }
        (output_dir / "report_stage.tex").write_text(_pending_macros(), encoding="utf-8")
        (output_dir / "result_table.tex").write_text(
            "% Results are intentionally unavailable in pending mode.\n", encoding="utf-8"
        )
        (output_dir / "result_paired_statistics.tex").write_text(
            "% Paired statistics are intentionally unavailable in pending mode.\n",
            encoding="utf-8",
        )
        (output_dir / "report_data.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return data

    if results_path is None:
        raise ReportInputError(f"stage {stage!r} requires an explicit completed results path")
    if statistics_path is None:
        raise ReportInputError(
            f"stage {stage!r} requires an explicit completed pairwise statistics path"
        )
    if matched_evidence_path is None:
        raise ReportInputError(
            f"stage {stage!r} requires an explicit matched raw-telemetry evidence path"
        )
    approved = validate_result_path(results_path, stage=stage, project_root=project_root)
    approved_statistics = validate_statistics_path(
        statistics_path, stage=stage, project_root=project_root
    )
    approved_evidence = validate_matched_evidence_path(
        matched_evidence_path, stage=stage, project_root=project_root
    )
    if len({approved.parent, approved_statistics.parent, approved_evidence.parent}) != 1:
        raise ReportInputError(
            "results, paired statistics, and matched evidence must be immutable siblings"
        )
    conditions = 120 if stage == "test" else 72
    if expected_conditions is not None and expected_conditions != conditions:
        raise ReportInputError(
            f"stage {stage!r} has a fixed condition count of {conditions}; "
            f"received {expected_conditions}"
        )
    results = pd.read_parquet(approved)
    validate_results(results, stage=stage, expected_conditions=conditions)
    results_sha256 = _sha256(approved)
    statistics_payload = json.loads(approved_statistics.read_text(encoding="utf-8"))
    paired_comparisons = validate_statistics(
        statistics_payload,
        results=results,
        expected_conditions=conditions,
    )
    joint_success_efficiency = validate_joint_success_efficiency(
        statistics_payload,
        results=results,
        expected_conditions=conditions,
    )
    matched_payload = json.loads(approved_evidence.read_text(encoding="utf-8"))
    matched_summary = validate_matched_evidence(
        matched_payload,
        results=results,
        results_sha256=results_sha256,
        stage=stage,
        evidence_path=approved_evidence,
    )
    valid = _valid_rows(results)
    summary = _method_summary(results)
    data = {
        "schema_version": 3,
        "stage": stage,
        "results_available": True,
        "public_name": PUBLIC_NAME,
        "benchmark_id": BENCHMARK_ID,
        "results_path": approved.relative_to(project_root).as_posix(),
        "results_sha256": results_sha256,
        "statistics_path": approved_statistics.relative_to(project_root).as_posix(),
        "statistics_sha256": _sha256(approved_statistics),
        "matched_evidence_path": approved_evidence.relative_to(project_root).as_posix(),
        "matched_evidence_sha256": _sha256(approved_evidence),
        "matched_run_evidence": {"available": True, **matched_summary},
        "runtime_capture": runtime_summary,
        "condition_count": conditions,
        "episode_count": len(results),
        "valid_episode_count": len(valid),
        "excluded_episode_count": int(len(results) - len(valid)),
        "method_summary": summary,
        "density_summary": _density_summary(results),
        "family_summary": _family_summary(results),
        "paired_effects": _paired_effects(results),
        "base_pgrr_planner_failure": _base_pgrr_planner_failure(results),
        "base_pgrr_joint_success_efficiency": joint_success_efficiency,
        "paired_comparisons": paired_comparisons,
        "author_alias": "Charles Chen",
    }
    _configure_plotting()
    _outcome_figure(results, output_dir)
    _density_figure(results, output_dir)
    _family_figure(results, output_dir)
    _safety_efficiency_figure(results, output_dir)
    _paired_effect_figure(paired_comparisons, output_dir)
    _joint_success_efficiency_figure(joint_success_efficiency, output_dir)
    if stage == "test":
        _copy_fixed_test_media(
            matched_summary,
            evidence_path=approved_evidence,
            output_dir=output_dir,
        )
    else:
        _matched_run_figure(matched_payload, output_dir)
    (output_dir / "result_table.tex").write_text(_result_table(summary), encoding="utf-8")
    (output_dir / "result_paired_statistics.tex").write_text(
        _paired_statistics_table(paired_comparisons), encoding="utf-8"
    )
    (output_dir / "report_stage.tex").write_text(_result_macros(data), encoding="utf-8")
    (output_dir / "report_data.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return data


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("pending", "validation", "test"), default="pending")
    parser.add_argument("--results", type=Path)
    parser.add_argument("--statistics", type=Path)
    parser.add_argument("--matched-evidence", type=Path)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "report/generated")
    parser.add_argument("--expected-conditions", type=int)
    parser.add_argument("--require-runtime-capture", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        data = build_report_assets(
            stage=args.stage,
            results_path=args.results,
            output_dir=args.output_dir,
            statistics_path=args.statistics,
            matched_evidence_path=args.matched_evidence,
            expected_conditions=args.expected_conditions,
            require_runtime_capture=args.require_runtime_capture,
        )
    except (ReportInputError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        f"Report assets PASS: stage={data['stage']}, results_available={data['results_available']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
