#!/usr/bin/env python3
"""Validate and expose the locked five-method moderate paper artifacts.

This module is deliberately read-only.  It cross-checks the episode-level
Parquet, the complete outcome-cell summary, and the paired-statistics JSON
before either the figure or table generator is allowed to render numbers.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

METHODS = ("base", "standard", "heuristic", "bc_uniform", "pgrr")
METHOD_LABELS = {
    "base": "DWB",
    "standard": "Standard",
    "heuristic": "Heuristic",
    "bc_uniform": "Uniform BC",
    "pgrr": "PGRR",
}

ALGORITHM_OUTCOMES = ("GOAL_REACHED", "COLLISION", "TIMEOUT", "PLANNER_FAILURE")
EXCLUDED_OUTCOMES = ("SIMULATOR_FAILURE", "INVALID_RESET")
KNOWN_OUTCOMES = (*ALGORITHM_OUTCOMES, *EXCLUDED_OUTCOMES)
DENSITY_ORDER = ("low", "medium", "high")
FAMILY_ORDER = (
    "head_on_corridor",
    "doorway_bottleneck",
    "crossing_flow",
    "blind_corner",
    "group_blocking",
    "overtaking",
    "opposite_streams",
    "temporary_blockage",
)

PROJECT_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")

# These fields define one physical evaluation condition and therefore must not
# change when only the evaluated method changes.  Optional provenance fields
# are checked whenever the result collector supplies them.
PAIR_INVARIANT_COLUMNS = (
    "scenario_id",
    "family",
    "density",
    "seed",
    "split",
    "replicate",
    "repeat",
    "run_index",
    "map",
    "map_id",
    "scenario",
    "robot_start",
    "robot_goal",
    "pedestrian_config_hash",
    "scenario_path",
    "scenario_sha256",
    "planner_id",
    "timeout_s",
)

RESULT_COLUMNS = {
    "episode_id",
    "pair_id",
    "scenario_id",
    "family",
    "density",
    "seed",
    "split",
    "source_policy",
    "outcome",
    "project_commit",
    "episode_duration_s",
    "navigation_time_s",
    "path_length_m",
    "spl",
    "min_human_distance_m",
    "human_distance_coverage_ratio",
    "personal_space_violation_ratio",
    "discomfort_time_s",
    "emergency_stop_count",
    "recovery_trigger_count",
    "recovery_success_count",
    "recovery_success_rate",
    "recovery_duration_s",
    "intervention_ratio",
}
SUMMARY_COLUMNS = {
    "method",
    "split",
    "family",
    "density",
    "outcome",
    "manifest_episode_count",
    "valid_episode_count",
    "excluded_episode_count",
    "outcome_count",
    "outcome_rate",
    "rate_denominator",
}


class ModerateArtifactError(RuntimeError):
    """Raised when a moderate paper artifact is incomplete or inconsistent."""


def display_method(method: object) -> str:
    """Return the fixed, paper-facing name for a registered method."""

    key = str(method).strip()
    return METHOD_LABELS.get(key, key.replace("_", " "))


def method_order(methods: Sequence[object]) -> list[str]:
    """Order methods according to the preregistered comparison protocol."""

    present = {str(value) for value in methods}
    return [method for method in METHODS if method in present]


def valid_mask(results: pd.DataFrame) -> pd.Series:
    """Return rows included in algorithm metrics and check exclusion semantics."""

    expected = ~results["outcome"].isin(EXCLUDED_OUTCOMES)
    if "included_in_algorithm_metrics" not in results:
        return expected
    raw = results["included_in_algorithm_metrics"]
    if not pd.api.types.is_bool_dtype(raw.dtype):
        if not bool(raw.isin((True, False)).all()):
            raise ModerateArtifactError("included_in_algorithm_metrics must be boolean")
    declared = raw.astype(bool)
    if not bool((declared == expected).all()):
        raise ModerateArtifactError(
            "included_in_algorithm_metrics disagrees with terminal outcome semantics"
        )
    return declared


def _pair_columns(results: pd.DataFrame) -> list[str]:
    # Publication inputs require the immutable identifier emitted by the
    # experiment manifest; heuristic fallback pairing is intentionally not
    # allowed here.
    if "pair_id" not in results or not bool(results["pair_id"].notna().all()):
        raise ModerateArtifactError("publication results require a non-null pair_id")
    return ["pair_id"]


def _metadata_token(value: object) -> str:
    """Return a stable comparison token for scalar or structured metadata."""

    if isinstance(value, np.ndarray):
        value = value.tolist()
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    try:
        if bool(pd.isna(value)):
            return "<NULL>"
    except (TypeError, ValueError):
        pass
    if isinstance(value, (float, np.floating)):
        return format(float(value), ".17g")
    return str(value)


def _validate_pair_metadata(results: pd.DataFrame, methods: Sequence[str]) -> None:
    pair_columns = [column for column in PAIR_INVARIANT_COLUMNS if column in results]
    for pair_id, group in results.groupby("pair_id", sort=False, dropna=False):
        observed_methods = set(group["source_policy"])
        if len(group) != len(methods) or observed_methods != set(methods):
            raise ModerateArtifactError(
                "each pair_id must contain exactly one row for every registered method; "
                f"pair_id={pair_id!r}, methods={sorted(observed_methods)}"
            )
        for column in pair_columns:
            tokens = group[column].map(_metadata_token)
            if int(tokens.nunique(dropna=False)) != 1:
                values = sorted(set(tokens.astype(str)))
                raise ModerateArtifactError(
                    "pair metadata mismatch across methods; "
                    f"pair_id={pair_id!r}, column={column}, values={values}"
                )


def _require_finite_nonnegative(
    results: pd.DataFrame,
    valid: pd.Series,
    columns: Sequence[str],
    *,
    artifact: Path,
) -> None:
    for column in columns:
        values = results.loc[valid, column].to_numpy(dtype=float)
        if not bool(np.isfinite(values).all()):
            raise ModerateArtifactError(f"valid episodes require finite {column}")
        if bool((values < 0.0).any()):
            raise ModerateArtifactError(f"{artifact} contains negative {column}")


def _validate_numeric_metrics(results: pd.DataFrame, *, artifact: Path) -> None:
    valid = results["_valid"]
    _require_finite_nonnegative(
        results,
        valid,
        (
            "episode_duration_s",
            "navigation_time_s",
            "path_length_m",
            "min_human_distance_m",
            "discomfort_time_s",
            "emergency_stop_count",
            "recovery_trigger_count",
            "recovery_success_count",
            "recovery_duration_s",
        ),
        artifact=artifact,
    )
    for column in (
        "spl",
        "human_distance_coverage_ratio",
        "personal_space_violation_ratio",
        "intervention_ratio",
    ):
        values = results.loc[valid, column].to_numpy(dtype=float)
        if not bool(np.isfinite(values).all()):
            raise ModerateArtifactError(f"valid episodes require finite {column}")
        if bool(((values < 0.0) | (values > 1.0)).any()):
            raise ModerateArtifactError(f"{artifact} contains {column} outside [0, 1]")

    for column in (
        "emergency_stop_count",
        "recovery_trigger_count",
        "recovery_success_count",
    ):
        values = results.loc[valid, column].to_numpy(dtype=float)
        if not bool(np.equal(values, np.floor(values)).all()):
            raise ModerateArtifactError(f"{artifact} contains non-integer {column}")

    triggers = results.loc[valid, "recovery_trigger_count"].to_numpy(dtype=float)
    successes = results.loc[valid, "recovery_success_count"].to_numpy(dtype=float)
    rates = results.loc[valid, "recovery_success_rate"].to_numpy(dtype=float)
    if bool((successes > triggers).any()):
        raise ModerateArtifactError("recovery successes cannot exceed recovery triggers")
    triggered = triggers > 0.0
    if not bool(np.isfinite(rates[triggered]).all()):
        raise ModerateArtifactError("triggered episodes require finite recovery_success_rate")
    if bool(((rates[triggered] < 0.0) | (rates[triggered] > 1.0)).any()):
        raise ModerateArtifactError(f"{artifact} contains recovery_success_rate outside [0, 1]")
    if bool(np.isfinite(rates[~triggered]).any()):
        raise ModerateArtifactError(
            "recovery_success_rate must be undefined when recovery_trigger_count is zero"
        )
    expected_rates = np.divide(
        successes[triggered],
        triggers[triggered],
        out=np.zeros_like(successes[triggered]),
        where=triggers[triggered] > 0.0,
    )
    if not bool(np.allclose(rates[triggered], expected_rates, rtol=1.0e-9, atol=1.0e-12)):
        raise ModerateArtifactError(
            "recovery_success_rate disagrees with recovery success/trigger counts"
        )


def _normalise_results(
    frame: pd.DataFrame,
    *,
    artifact: Path,
    methods: Sequence[str],
    expected_condition_count: int,
) -> pd.DataFrame:
    if (
        isinstance(expected_condition_count, bool)
        or not isinstance(expected_condition_count, (int, np.integer))
        or expected_condition_count <= 0
    ):
        raise ModerateArtifactError("expected_condition_count must be a positive integer")
    missing = sorted(RESULT_COLUMNS - set(frame.columns))
    if missing:
        raise ModerateArtifactError(f"{artifact} is missing required columns: {', '.join(missing)}")
    if frame.empty:
        raise ModerateArtifactError(f"{artifact} contains no episode results")
    results = frame.copy()
    for column in (
        "episode_id",
        "pair_id",
        "scenario_id",
        "family",
        "density",
        "split",
        "source_policy",
        "outcome",
        "project_commit",
    ):
        if bool(results[column].isna().any()):
            raise ModerateArtifactError(f"{artifact} contains a null {column}")
        results[column] = results[column].astype(str).str.strip()
        if bool(results[column].eq("").any()):
            raise ModerateArtifactError(f"{artifact} contains an empty {column}")
    results["outcome"] = results["outcome"].str.upper().str.replace(" ", "_", regex=False)
    unknown_outcomes = sorted(set(results["outcome"]) - set(KNOWN_OUTCOMES))
    if unknown_outcomes:
        raise ModerateArtifactError(
            f"{artifact} contains unknown outcomes: {', '.join(unknown_outcomes)}"
        )
    if bool(results["episode_id"].duplicated(keep=False).any()):
        duplicate_id = str(results.loc[results["episode_id"].duplicated(), "episode_id"].iloc[0])
        raise ModerateArtifactError(f"episode_id values must be globally unique: {duplicate_id}")
    commits = sorted(set(results["project_commit"].str.lower()))
    if len(commits) != 1 or PROJECT_COMMIT_PATTERN.fullmatch(commits[0]) is None:
        raise ModerateArtifactError(
            "publication results require one uniform nonempty 40-hex project_commit"
        )
    results["project_commit"] = commits[0]
    present_methods = set(results["source_policy"])
    if present_methods != set(methods):
        missing_methods = sorted(set(methods) - present_methods)
        extra_methods = sorted(present_methods - set(methods))
        raise ModerateArtifactError(
            "results must contain exactly the registered methods; "
            f"missing={missing_methods}, extra={extra_methods}"
        )
    splits = sorted(set(results["split"].str.lower()))
    if splits != ["test"]:
        raise ModerateArtifactError(
            f"publication artifacts require exactly the test split; observed={splits}"
        )
    results["split"] = "test"
    families = set(results["family"])
    if families != set(FAMILY_ORDER):
        raise ModerateArtifactError(
            "publication results require exactly the eight registered families; "
            f"missing={sorted(set(FAMILY_ORDER) - families)}, "
            f"extra={sorted(families - set(FAMILY_ORDER))}"
        )
    densities = set(results["density"])
    if densities != set(DENSITY_ORDER):
        raise ModerateArtifactError(
            "publication results require exactly low/medium/high density; "
            f"missing={sorted(set(DENSITY_ORDER) - densities)}, "
            f"extra={sorted(densities - set(DENSITY_ORDER))}"
        )

    seeds = pd.to_numeric(results["seed"], errors="coerce").to_numpy(dtype=float)
    if not bool(np.isfinite(seeds).all()) or not bool(np.equal(seeds, np.floor(seeds)).all()):
        raise ModerateArtifactError(f"{artifact} requires finite integer seeds")
    results["seed"] = seeds.astype(np.int64)
    if "method" in results:
        if bool(results["method"].isna().any()):
            raise ModerateArtifactError(f"{artifact} contains a null method")
        declared_methods = results["method"].astype(str).str.strip()
        if not bool(declared_methods.eq(results["source_policy"]).all()):
            raise ModerateArtifactError("method must exactly match source_policy on every row")

    pair_columns = _pair_columns(results)
    duplicate = results.duplicated(subset=["source_policy", *pair_columns], keep=False)
    if bool(duplicate.any()):
        example = results.loc[duplicate, ["source_policy", *pair_columns]].iloc[0].to_dict()
        raise ModerateArtifactError(f"duplicate method/condition row: {example}")
    condition_sets = {
        method: set(
            map(
                tuple,
                results.loc[results["source_policy"] == method, pair_columns].itertuples(
                    index=False,
                    name=None,
                ),
            )
        )
        for method in methods
    }
    expected = condition_sets[methods[-1]]
    if not expected:
        raise ModerateArtifactError("the proposed method contains no conditions")
    for method, conditions in condition_sets.items():
        if conditions != expected:
            raise ModerateArtifactError(
                "all five methods must use the identical preregistered condition set; "
                f"method={method}, missing={len(expected - conditions)}, "
                f"extra={len(conditions - expected)}"
            )
    if len(expected) != expected_condition_count:
        raise ModerateArtifactError(
            "condition count disagrees with the explicitly declared publication protocol; "
            f"expected={expected_condition_count}, observed={len(expected)}"
        )
    cell_count = len(FAMILY_ORDER) * len(DENSITY_ORDER)
    repetitions, remainder = divmod(expected_condition_count, cell_count)
    if remainder or repetitions <= 0:
        raise ModerateArtifactError(
            "expected_condition_count must be a positive balanced multiple of "
            f"{cell_count} family-density cells"
        )
    proposed = results.loc[results["source_policy"] == methods[-1]]
    observed_cells = proposed.groupby(["family", "density"], observed=True).size()
    expected_cells = {(family, density) for family in FAMILY_ORDER for density in DENSITY_ORDER}
    if set(observed_cells.index) != expected_cells or not bool(
        observed_cells.eq(repetitions).all()
    ):
        raise ModerateArtifactError(
            "publication conditions must be balanced across all family-density cells; "
            f"expected_repetitions_per_cell={repetitions}"
        )
    _validate_pair_metadata(results, methods)

    results["_valid"] = valid_mask(results)
    numeric_columns = (
        "seed",
        "min_human_distance_m",
        "episode_duration_s",
        "navigation_time_s",
        "spl",
        "path_length_m",
        "human_distance_coverage_ratio",
        "personal_space_violation_ratio",
        "discomfort_time_s",
        "emergency_stop_count",
        "recovery_trigger_count",
        "recovery_success_count",
        "recovery_success_rate",
        "recovery_duration_s",
        "intervention_ratio",
        "mean_abs_angular_jerk_rad_s3",
    )
    for column in numeric_columns:
        if column in results:
            results[column] = pd.to_numeric(results[column], errors="coerce")
    _validate_numeric_metrics(results, artifact=artifact)
    return results


def _expected_summary(results: pd.DataFrame, methods: Sequence[str]) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for key, group in results.groupby(
        ["source_policy", "split", "family", "density"],
        sort=True,
        dropna=False,
    ):
        method, split, family, density = map(str, key)
        valid = group.loc[group["_valid"]]
        for outcome in KNOWN_OUTCOMES:
            count = int((group["outcome"] == outcome).sum())
            denominator = len(valid) if outcome in ALGORITHM_OUTCOMES else len(group)
            records.append(
                {
                    "method": method,
                    "split": split,
                    "family": family,
                    "density": density,
                    "outcome": outcome,
                    "manifest_episode_count": len(group),
                    "valid_episode_count": len(valid),
                    "excluded_episode_count": len(group) - len(valid),
                    "outcome_count": count,
                    "outcome_rate": count / denominator if denominator else np.nan,
                    "rate_denominator": (
                        "valid_episodes" if outcome in ALGORITHM_OUTCOMES else "manifest_episodes"
                    ),
                }
            )
    return pd.DataFrame.from_records(records)


def _validate_summary(
    frame: pd.DataFrame,
    *,
    results: pd.DataFrame,
    artifact: Path,
    methods: Sequence[str],
) -> pd.DataFrame:
    missing = sorted(SUMMARY_COLUMNS - set(frame.columns))
    if missing:
        raise ModerateArtifactError(f"{artifact} is missing required columns: {', '.join(missing)}")
    summary = frame.copy()
    if summary.empty:
        raise ModerateArtifactError(f"{artifact} contains no summary cells")
    if set(summary["method"].astype(str)) != set(methods):
        raise ModerateArtifactError("summary method set does not match results")
    keys = ["method", "split", "family", "density", "outcome"]
    if bool(summary.duplicated(subset=keys, keep=False).any()):
        raise ModerateArtifactError(
            "summary contains duplicate method/family/density/outcome cells"
        )
    expected = _expected_summary(results, methods)
    observed = summary.merge(
        expected, on=keys, how="outer", suffixes=("_obs", "_exp"), indicator=True
    )
    if not bool(observed["_merge"].eq("both").all()):
        raise ModerateArtifactError("summary cells do not exactly cover the results cells")
    for column in (
        "manifest_episode_count",
        "valid_episode_count",
        "excluded_episode_count",
        "outcome_count",
    ):
        left = pd.to_numeric(observed[f"{column}_obs"], errors="coerce")
        right = pd.to_numeric(observed[f"{column}_exp"], errors="coerce")
        if not bool(left.eq(right).all()):
            raise ModerateArtifactError(f"summary {column} disagrees with results")
    observed_rate = pd.to_numeric(observed["outcome_rate_obs"], errors="coerce")
    expected_rate = pd.to_numeric(observed["outcome_rate_exp"], errors="coerce")
    if not bool(
        np.allclose(
            observed_rate.to_numpy(dtype=float),
            expected_rate.to_numpy(dtype=float),
            rtol=1.0e-9,
            atol=1.0e-12,
            equal_nan=True,
        )
    ):
        raise ModerateArtifactError("summary outcome rates disagree with results")
    if not bool(observed["rate_denominator_obs"].eq(observed["rate_denominator_exp"]).all()):
        raise ModerateArtifactError("summary rate denominators disagree with results")
    return summary


def _validate_statistics(
    payload: object,
    *,
    results: pd.DataFrame,
    artifact: Path,
    methods: Sequence[str],
) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise ModerateArtifactError(f"{artifact} does not contain successful statistics")
    if payload.get("main_method") != "pgrr":
        raise ModerateArtifactError("pairwise statistics must use pgrr as the main method")
    if list(payload.get("methods", [])) != list(methods):
        raise ModerateArtifactError("statistics method order does not match the paper protocol")
    comparators = [method for method in methods if method != "pgrr"]
    if list(payload.get("comparators", [])) != comparators:
        raise ModerateArtifactError("statistics comparator list is incomplete or reordered")
    comparisons = payload.get("comparisons")
    if not isinstance(comparisons, Mapping) or set(comparisons) != set(comparators):
        raise ModerateArtifactError("statistics comparisons do not cover all four baselines")
    condition_count = len(results) // len(methods)
    analysis_policy = payload.get("analysis_policy")
    if not isinstance(analysis_policy, Mapping):
        raise ModerateArtifactError("statistics omit analysis policy provenance")
    if int(analysis_policy.get("condition_count", -1)) != condition_count:
        raise ModerateArtifactError("statistics condition count disagrees with results")
    if bool(analysis_policy.get("scenario_or_seed_filtering", True)):
        raise ModerateArtifactError("statistics must explicitly prohibit scenario/seed filtering")

    global_tests = payload.get("global_multiple_comparison")
    if not isinstance(global_tests, Mapping) or global_tests.get("method") != "Holm":
        raise ModerateArtifactError("statistics must include the global Holm family")
    hypotheses = global_tests.get("hypotheses")
    if not isinstance(hypotheses, list):
        raise ModerateArtifactError("statistics global Holm family is malformed")
    global_evidence: dict[str, Mapping[str, Any]] = {}
    for row in hypotheses:
        if not isinstance(row, Mapping):
            raise ModerateArtifactError("statistics global Holm rows must be objects")
        name = str(row.get("hypothesis", ""))
        if not name or name in global_evidence:
            raise ModerateArtifactError("statistics global Holm hypotheses must be unique")
        global_evidence[name] = row

    pair_columns = _pair_columns(results)
    pgrr = results.loc[
        results["source_policy"] == "pgrr",
        [
            *pair_columns,
            "_valid",
            "outcome",
            "episode_duration_s",
            "path_length_m",
        ],
    ]
    for comparator in comparators:
        comparison = comparisons[comparator]
        if not isinstance(comparison, Mapping) or comparison.get("status") != "ok":
            raise ModerateArtifactError(f"statistics comparison {comparator} is not successful")
        if (
            comparison.get("reference_policy") != comparator
            or comparison.get("treatment_policy") != "pgrr"
        ):
            raise ModerateArtifactError(f"statistics direction is invalid for {comparator}")
        binary = comparison.get("binary_outcomes")
        if not isinstance(binary, Mapping):
            raise ModerateArtifactError(f"statistics omit binary endpoints for {comparator}")
        comparator_rows = results.loc[
            results["source_policy"] == comparator,
            [
                *pair_columns,
                "_valid",
                "outcome",
                "episode_duration_s",
                "path_length_m",
            ],
        ]
        paired = comparator_rows.merge(
            pgrr,
            on=pair_columns,
            how="inner",
            validate="one_to_one",
            suffixes=("_reference", "_treatment"),
        )
        paired_valid = paired["_valid_reference"] & paired["_valid_treatment"]
        expected_pairs = int(paired_valid.sum())
        if int(comparison.get("valid_pair_count", -1)) != expected_pairs:
            raise ModerateArtifactError(f"statistics valid-pair count disagrees for {comparator}")
        complete = paired.loc[paired_valid]
        for key, outcome in (
            ("goal_reached", "GOAL_REACHED"),
            ("collision", "COLLISION"),
            ("timeout", "TIMEOUT"),
        ):
            endpoint = binary.get(key)
            if not isinstance(endpoint, Mapping):
                raise ModerateArtifactError(f"statistics omit {key} for {comparator}")
            if int(endpoint.get("pair_count", -1)) != expected_pairs:
                raise ModerateArtifactError(
                    f"statistics pair count disagrees for {comparator}/{key}"
                )
            for field in ("difference_treatment_minus_reference", "mcnemar_exact"):
                if not isinstance(endpoint.get(field), Mapping):
                    raise ModerateArtifactError(f"statistics omit {field} for {comparator}/{key}")
            interval = endpoint["difference_treatment_minus_reference"]
            values = [interval.get(name) for name in ("estimate", "lower", "upper")]
            if any(value is None or not math.isfinite(float(value)) for value in values):
                raise ModerateArtifactError(f"non-finite interval for {comparator}/{key}")
            estimate, lower, upper = map(float, values)
            if not lower <= estimate <= upper:
                raise ModerateArtifactError(
                    f"confidence interval does not contain estimate for {comparator}/{key}"
                )
            reference_count = int((complete["outcome_reference"] == outcome).sum())
            treatment_count = int((complete["outcome_treatment"] == outcome).sum())
            reference_rate = reference_count / expected_pairs
            treatment_rate = treatment_count / expected_pairs
            deterministic = {
                "reference_count": reference_count,
                "treatment_count": treatment_count,
                "reference_rate": reference_rate,
                "treatment_rate": treatment_rate,
            }
            for field, expected_value in deterministic.items():
                observed_value = endpoint.get(field)
                if observed_value is None or not np.isclose(
                    float(observed_value),
                    float(expected_value),
                    rtol=1.0e-9,
                    atol=1.0e-12,
                ):
                    raise ModerateArtifactError(
                        f"statistics {field} disagrees for {comparator}/{key}"
                    )
            if not np.isclose(
                estimate,
                treatment_rate - reference_rate,
                rtol=1.0e-9,
                atol=1.0e-12,
            ):
                raise ModerateArtifactError(
                    f"statistics difference estimate disagrees for {comparator}/{key}"
                )
            test = endpoint["mcnemar_exact"]
            for field in ("pvalue_raw", "pvalue_holm"):
                value = test.get(field)
                if (
                    value is None
                    or not math.isfinite(float(value))
                    or not 0.0 <= float(value) <= 1.0
                ):
                    raise ModerateArtifactError(
                        f"statistics {field} is invalid for {comparator}/{key}"
                    )
        if comparator != "base":
            continue
        continuous = comparison.get("continuous_metrics")
        if not isinstance(continuous, Mapping):
            raise ModerateArtifactError("statistics omit continuous metrics for base")
        joint_success = complete.loc[
            (complete["outcome_reference"] == "GOAL_REACHED")
            & (complete["outcome_treatment"] == "GOAL_REACHED")
        ]
        for metric, column in (
            ("successful_episode_duration_s", "episode_duration_s"),
            ("successful_path_length_m", "path_length_m"),
        ):
            analysis = continuous.get(metric)
            if not isinstance(analysis, Mapping):
                raise ModerateArtifactError(f"statistics omit base/{metric}")
            if analysis.get("population") != "joint_success":
                raise ModerateArtifactError(f"statistics {metric} must use joint_success pairs")
            reference_values = joint_success[f"{column}_reference"].to_numpy(dtype=float)
            treatment_values = joint_success[f"{column}_treatment"].to_numpy(dtype=float)
            finite = np.isfinite(reference_values) & np.isfinite(treatment_values)
            reference_values = reference_values[finite]
            treatment_values = treatment_values[finite]
            expected_count = int(reference_values.size)
            if int(analysis.get("pair_count", -1)) != expected_count:
                raise ModerateArtifactError(f"statistics pair count disagrees for base/{metric}")
            if expected_count == 0:
                if analysis.get("status") != "insufficient_finite_pairs":
                    raise ModerateArtifactError(
                        f"statistics base/{metric} must declare insufficient finite pairs"
                    )
                continue
            if analysis.get("status") != "ok":
                raise ModerateArtifactError(f"statistics base/{metric} is not successful")
            for field, expected_value in (
                ("reference_mean", float(np.mean(reference_values))),
                ("treatment_mean", float(np.mean(treatment_values))),
            ):
                observed_value = analysis.get(field)
                if observed_value is None or not np.isclose(
                    float(observed_value), expected_value, rtol=1.0e-9, atol=1.0e-12
                ):
                    raise ModerateArtifactError(f"statistics {field} disagrees for base/{metric}")
            interval = analysis.get("difference_treatment_minus_reference")
            if not isinstance(interval, Mapping):
                raise ModerateArtifactError(f"statistics omit paired difference for base/{metric}")
            interval_values = [interval.get(field) for field in ("estimate", "lower", "upper")]
            if any(value is None or not math.isfinite(float(value)) for value in interval_values):
                raise ModerateArtifactError(f"statistics interval is invalid for base/{metric}")
            estimate, lower, upper = map(float, interval_values)
            expected_difference = float(np.mean(treatment_values - reference_values))
            if not np.isclose(estimate, expected_difference, rtol=1.0e-9, atol=1.0e-12):
                raise ModerateArtifactError(
                    f"statistics difference estimate disagrees for base/{metric}"
                )
            if not lower <= estimate <= upper:
                raise ModerateArtifactError(
                    f"confidence interval does not contain estimate for base/{metric}"
                )
            test = analysis.get("wilcoxon")
            if not isinstance(test, Mapping):
                raise ModerateArtifactError(f"statistics omit Wilcoxon test for base/{metric}")
            for field in ("pvalue_raw", "pvalue_holm"):
                value = test.get(field)
                if (
                    value is None
                    or not math.isfinite(float(value))
                    or not 0.0 <= float(value) <= 1.0
                ):
                    raise ModerateArtifactError(f"statistics {field} is invalid for base/{metric}")
            hypothesis = f"base::wilcoxon_{metric}"
            global_row = global_evidence.get(hypothesis)
            if (
                global_row is None
                or not np.isclose(
                    float(global_row.get("pvalue_raw", math.nan)),
                    float(test["pvalue_raw"]),
                    rtol=1.0e-9,
                    atol=1.0e-12,
                )
                or not np.isclose(
                    float(global_row.get("pvalue_holm_global", math.nan)),
                    float(test["pvalue_holm"]),
                    rtol=1.0e-9,
                    atol=1.0e-12,
                )
            ):
                raise ModerateArtifactError(
                    f"statistics global Holm row disagrees for {hypothesis}"
                )
    return dict(payload)


def load_moderate_artifacts(
    results_path: Path,
    summary_path: Path,
    statistics_path: Path,
    *,
    expected_condition_count: int,
    methods: Sequence[str] = METHODS,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Load and cross-check all immutable moderate paper inputs."""

    paths = (results_path, summary_path, statistics_path)
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise ModerateArtifactError("missing locked moderate artifact(s): " + ", ".join(missing))
    if tuple(methods) != METHODS:
        raise ModerateArtifactError(
            "publication generation requires base, standard, heuristic, bc_uniform, pgrr"
        )
    try:
        results_frame = pd.read_parquet(results_path)
        summary_frame = pd.read_csv(summary_path)
        statistics_payload = json.loads(statistics_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError, pd.errors.ParserError) as error:
        raise ModerateArtifactError(f"failed to read moderate artifacts: {error}") from error
    results = _normalise_results(
        results_frame,
        artifact=results_path,
        methods=methods,
        expected_condition_count=expected_condition_count,
    )
    summary = _validate_summary(
        summary_frame,
        results=results,
        artifact=summary_path,
        methods=methods,
    )
    statistics = _validate_statistics(
        statistics_payload,
        results=results,
        artifact=statistics_path,
        methods=methods,
    )
    return results, summary, statistics


def wilson_interval(successes: int, total: int) -> tuple[float, float, float]:
    """Return a binomial rate and two-sided 95% Wilson interval."""

    if total <= 0 or not 0 <= successes <= total:
        return (math.nan, math.nan, math.nan)
    proportion = successes / total
    z_value = 1.959963984540054
    denominator = 1.0 + z_value**2 / total
    center = (proportion + z_value**2 / (2.0 * total)) / denominator
    radius = (
        z_value
        * math.sqrt(proportion * (1.0 - proportion) / total + z_value**2 / (4.0 * total**2))
        / denominator
    )
    return proportion, max(0.0, center - radius), min(1.0, center + radius)


def bootstrap_median(
    values: Sequence[float] | np.ndarray,
    *,
    seed: int,
    samples: int = 4_000,
) -> tuple[float, float, float]:
    """Return a median and deterministic percentile-bootstrap 95% interval."""

    array = np.asarray(values, dtype=float)
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return (math.nan, math.nan, math.nan)
    estimate = float(np.median(finite))
    if finite.size == 1:
        return estimate, estimate, estimate
    generator = np.random.default_rng(seed)
    indices = generator.integers(0, finite.size, size=(samples, finite.size))
    distribution = np.median(finite[indices], axis=1)
    lower, upper = np.quantile(distribution, (0.025, 0.975))
    return estimate, float(lower), float(upper)


def latex_escape(value: object) -> str:
    """Escape a plain-text value for a LaTeX table cell."""

    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in str(value))


def portable_path(path: Path, root: Path = ROOT) -> str:
    """Return privacy-safe provenance relative to the repository."""

    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(root.expanduser().resolve()).as_posix()
    except ValueError:
        return f"${{PROJECT_ROOT}}/external/{resolved.name}"
