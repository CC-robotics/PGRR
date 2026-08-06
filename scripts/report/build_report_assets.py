#!/usr/bin/env python3
# ruff: noqa: RUF001
"""Build stage-aware report assets without consulting unapproved results.

The default ``pending`` stage is deliberately data free.  Result-bearing
stages require both a completed episode-level Parquet and its sibling
``pairwise_statistics.json``.  Historical, pilot, calibration, smoke, and
live validation paths are rejected before a file is opened.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager

PROJECT_ROOT = Path(__file__).resolve().parents[2]
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
        "pair_id",
        "scenario_id",
        "family",
        "density",
        "seed",
        "split",
        "source_policy",
        "outcome",
        "episode_duration_s",
        "navigation_time_s",
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
        for column in ("scenario_id", "family", "density", "seed", "split"):
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
\newcommand{\ReportStatisticsSha}{--}
"""


def _result_macros(data: Mapping[str, Any]) -> str:
    summary = {row["method"]: row for row in data["method_summary"]}
    base = summary["base"]
    pgrr = summary["pgrr"]
    stage_label = "锁定测试集结果" if data["stage"] == "test" else "验证集快照：非最终测试结论"
    notice = (
        "数值来自锁定 moderate-v5 test 结果。"
        if data["stage"] == "test"
        else "数值仅用于验证阶段汇报，不得表述为最终测试结论。"
    )
    goal_difference = 100.0 * float(data["paired_effects"]["goal_difference"])
    return "\n".join(
        (
            "% Generated from a policy-approved results.parquet.",
            r"\newif\ifReportResultsAvailable",
            r"\ReportResultsAvailabletrue",
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
    project_root: Path = PROJECT_ROOT,
    expected_conditions: int | None = None,
) -> dict[str, Any]:
    """Build deterministic report inputs and return their machine-readable data."""

    if stage not in {"pending", "validation", "test"}:
        raise ReportInputError("stage must be one of: pending, validation, test")
    output_dir.mkdir(parents=True, exist_ok=True)
    if stage == "pending":
        if results_path is not None or statistics_path is not None:
            raise ReportInputError(
                "pending stage must not receive or inspect result/statistics files"
            )
        data: dict[str, Any] = {
            "schema_version": 2,
            "stage": "pending",
            "results_available": False,
            "notice": "Validation is running; no numerical result is approved for reporting.",
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
    approved = validate_result_path(results_path, stage=stage, project_root=project_root)
    approved_statistics = validate_statistics_path(
        statistics_path, stage=stage, project_root=project_root
    )
    if approved.parent != approved_statistics.parent:
        raise ReportInputError("results and paired statistics must be immutable sibling artifacts")
    conditions = 120 if stage == "test" else 72
    if expected_conditions is not None and expected_conditions != conditions:
        raise ReportInputError(
            f"stage {stage!r} has a fixed condition count of {conditions}; "
            f"received {expected_conditions}"
        )
    results = pd.read_parquet(approved)
    validate_results(results, stage=stage, expected_conditions=conditions)
    statistics_payload = json.loads(approved_statistics.read_text(encoding="utf-8"))
    paired_comparisons = validate_statistics(
        statistics_payload,
        results=results,
        expected_conditions=conditions,
    )
    valid = _valid_rows(results)
    summary = _method_summary(results)
    data = {
        "schema_version": 2,
        "stage": stage,
        "results_available": True,
        "results_path": approved.relative_to(project_root).as_posix(),
        "results_sha256": _sha256(approved),
        "statistics_path": approved_statistics.relative_to(project_root).as_posix(),
        "statistics_sha256": _sha256(approved_statistics),
        "condition_count": conditions,
        "episode_count": len(results),
        "valid_episode_count": len(valid),
        "excluded_episode_count": int(len(results) - len(valid)),
        "method_summary": summary,
        "density_summary": _density_summary(results),
        "family_summary": _family_summary(results),
        "paired_effects": _paired_effects(results),
        "paired_comparisons": paired_comparisons,
        "author_alias": "Charles Chen",
    }
    _configure_plotting()
    _outcome_figure(results, output_dir)
    _density_figure(results, output_dir)
    _family_figure(results, output_dir)
    _safety_efficiency_figure(results, output_dir)
    _paired_effect_figure(paired_comparisons, output_dir)
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
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "report/generated")
    parser.add_argument("--expected-conditions", type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        data = build_report_assets(
            stage=args.stage,
            results_path=args.results,
            output_dir=args.output_dir,
            statistics_path=args.statistics,
            expected_conditions=args.expected_conditions,
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
