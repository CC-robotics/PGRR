#!/usr/bin/env python3
"""Summarize a preregistered moderate multi-baseline evaluation.

The input Parquet file is treated as an immutable, complete experiment table.
This tool intentionally exposes no scenario, family, density, or seed filters:
every requested method must contain the same condition keys as the proposed
method, and every valid row contributes to the summaries and paired tests.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd

STATISTICS_PATH = Path(__file__).with_name("statistics.py")

ALGORITHM_OUTCOMES = (
    "GOAL_REACHED",
    "COLLISION",
    "TIMEOUT",
    "PLANNER_FAILURE",
)
EXCLUDED_OUTCOMES = ("SIMULATOR_FAILURE", "INVALID_RESET")
KNOWN_OUTCOMES = (*ALGORITHM_OUTCOMES, *EXCLUDED_OUTCOMES)

SUMMARY_METRICS = (
    "episode_duration_s",
    "navigation_time_s",
    "spl",
    "path_length_m",
    "min_human_distance_m",
    "personal_space_violation_ratio",
    "discomfort_time_s",
    "emergency_stop_count",
    "recovery_trigger_count",
    "recovery_success_rate",
    "recovery_duration_s",
    "intervention_ratio",
    "mean_abs_angular_jerk_rad_s3",
)

CALIBRATION_THRESHOLDS: dict[str, float | int] = {
    "success_rate_min": 0.55,
    "success_rate_max": 0.75,
    "collision_plus_timeout_rate_min": 0.20,
    "collision_plus_timeout_rate_max": 0.45,
    "interaction_distance_m": 2.0,
    "interaction_episode_ratio_min": 0.80,
    "interaction_family_count_min": 6,
}


def _statistics_module() -> ModuleType:
    """Load the existing paired-statistics implementation without import ambiguity."""

    spec = importlib.util.spec_from_file_location("pgrr_moderate_statistics", STATISTICS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load statistics implementation: {STATISTICS_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _required_columns(results: pd.DataFrame) -> None:
    required = {
        "episode_id",
        "scenario_id",
        "family",
        "density",
        "seed",
        "split",
        "source_policy",
        "outcome",
        "min_human_distance_m",
    }
    missing = sorted(required - set(results.columns))
    if missing:
        raise ValueError(f"results are missing required columns: {', '.join(missing)}")
    if results.empty:
        raise ValueError("results contain no episodes")
    for column in ("episode_id", "scenario_id", "family", "density", "split", "source_policy"):
        values = results[column].astype(str).str.strip()
        if values.eq("").any():
            raise ValueError(f"results contain an empty {column}")
    unknown = sorted(set(results["outcome"].astype(str)) - set(KNOWN_OUTCOMES))
    if unknown:
        raise ValueError(f"results contain unknown outcomes: {', '.join(unknown)}")
    if "project_commit" in results.columns:
        commits = set(results["project_commit"].dropna().astype(str))
        if len(commits) > 1:
            raise ValueError("results mix multiple project commits")


def _valid_mask(results: pd.DataFrame) -> pd.Series:
    if "included_in_algorithm_metrics" in results.columns:
        values = results["included_in_algorithm_metrics"]
        if not pd.api.types.is_bool_dtype(values.dtype):
            allowed = values.isin((True, False))
            if not bool(allowed.all()):
                raise ValueError("included_in_algorithm_metrics must be boolean")
        mask = values.astype(bool)
    else:
        mask = ~results["outcome"].isin(EXCLUDED_OUTCOMES)
    inconsistent = mask & results["outcome"].isin(EXCLUDED_OUTCOMES)
    if bool(inconsistent.any()):
        raise ValueError("infrastructure outcomes cannot be included in algorithm metrics")
    return mask


def _method_order(
    results: pd.DataFrame,
    requested: Sequence[str] | None,
    *,
    main_method: str,
    reference_method: str,
) -> tuple[str, ...]:
    available = tuple(dict.fromkeys(results["source_policy"].astype(str)))
    methods = tuple(requested) if requested else available
    if not methods:
        raise ValueError("at least one method is required")
    if any(not method.strip() for method in methods):
        raise ValueError("method names must be non-empty")
    if len(set(methods)) != len(methods):
        raise ValueError("method list contains duplicates")
    missing = sorted(set(methods) - set(available))
    if missing:
        raise ValueError(f"requested methods are absent from results: {', '.join(missing)}")
    if main_method not in methods:
        raise ValueError(f"main method {main_method!r} is not in the method list")
    if reference_method not in methods:
        raise ValueError(f"reference method {reference_method!r} is not in the method list")
    if main_method == reference_method:
        raise ValueError("main and reference methods must differ")
    return methods


def _pairing_key_frame(
    results: pd.DataFrame, statistics: ModuleType
) -> tuple[pd.DataFrame, list[str]]:
    working, columns = statistics._pairing_columns(results)
    key_frame = working.loc[:, columns].copy()
    key_frame.columns = [column.lstrip("_") for column in columns]
    return key_frame, columns


def validate_complete_condition_sets(
    results: pd.DataFrame,
    *,
    methods: Sequence[str],
    main_method: str,
    statistics: ModuleType,
) -> dict[str, int]:
    """Require every selected method on every declared condition, without intersection."""

    selected = results.loc[results["source_policy"].isin(methods)].copy()
    keys, columns = _pairing_key_frame(selected, statistics)
    selected["_condition_key"] = list(map(tuple, keys.itertuples(index=False, name=None)))
    duplicate = selected.duplicated(subset=["source_policy", "_condition_key"], keep=False)
    if bool(duplicate.any()):
        example = selected.loc[duplicate, ["source_policy", "episode_id"]].iloc[0].to_dict()
        raise ValueError(f"duplicate method/condition row: {example}")
    condition_sets = {
        method: set(selected.loc[selected["source_policy"] == method, "_condition_key"])
        for method in methods
    }
    expected = condition_sets[main_method]
    if not expected:
        raise ValueError(f"main method {main_method!r} contains no conditions")
    for method, conditions in condition_sets.items():
        missing = expected - conditions
        extra = conditions - expected
        if missing or extra:
            raise ValueError(
                "all selected methods must have identical preregistered condition sets; "
                f"method={method!r}, missing={len(missing)}, extra={len(extra)}"
            )
    return {
        "condition_count": len(expected),
        "method_count": len(methods),
        "manifest_episode_count": len(selected),
        "pairing_column_count": len(columns),
    }


def _finite_mean(rows: pd.DataFrame, column: str) -> float | None:
    if column not in rows.columns or rows.empty:
        return None
    numeric = pd.to_numeric(rows[column], errors="coerce").to_numpy(dtype=np.float64)
    finite = numeric[np.isfinite(numeric)]
    return float(np.mean(finite)) if finite.size else None


def build_summary(results: pd.DataFrame, *, methods: Sequence[str]) -> pd.DataFrame:
    """Return complete method/split/family/density/outcome cells."""

    selected = results.loc[results["source_policy"].isin(methods)].copy()
    selected["_valid"] = _valid_mask(selected)
    records: list[dict[str, Any]] = []
    group_columns = ["source_policy", "split", "family", "density"]
    for key, group in selected.groupby(group_columns, dropna=False, sort=True):
        method, split, family, density = (str(value) for value in key)
        valid = group.loc[group["_valid"]]
        manifest_count = len(group)
        valid_count = len(valid)
        for outcome in KNOWN_OUTCOMES:
            outcome_rows = group.loc[group["outcome"] == outcome]
            algorithm_outcome = outcome in ALGORITHM_OUTCOMES
            denominator = valid_count if algorithm_outcome else manifest_count
            record: dict[str, Any] = {
                "method": method,
                "split": split,
                "family": family,
                "density": density,
                "outcome": outcome,
                "manifest_episode_count": manifest_count,
                "valid_episode_count": valid_count,
                "excluded_episode_count": manifest_count - valid_count,
                "scenario_count": int(group["scenario_id"].nunique()),
                "seed_count": int(group["seed"].nunique()),
                "outcome_count": len(outcome_rows),
                "outcome_rate": len(outcome_rows) / denominator if denominator else None,
                "rate_denominator": "valid_episodes" if algorithm_outcome else "manifest_episodes",
            }
            for metric in SUMMARY_METRICS:
                record[f"{metric}_mean"] = _finite_mean(outcome_rows, metric)
            records.append(record)
    columns = [
        "method",
        "split",
        "family",
        "density",
        "outcome",
        "manifest_episode_count",
        "valid_episode_count",
        "excluded_episode_count",
        "scenario_count",
        "seed_count",
        "outcome_count",
        "outcome_rate",
        "rate_denominator",
        *(f"{metric}_mean" for metric in SUMMARY_METRICS),
    ]
    return pd.DataFrame.from_records(records, columns=columns)


def _gate_check(
    *,
    name: str,
    value: float | int | None,
    minimum: float | int | None = None,
    maximum: float | int | None = None,
) -> dict[str, Any]:
    passed = value is not None
    if passed and minimum is not None:
        passed = bool(value >= minimum)
    if passed and maximum is not None:
        passed = bool(value <= maximum)
    return {
        "name": name,
        "value": value,
        "minimum_inclusive": minimum,
        "maximum_inclusive": maximum,
        "passed": passed,
    }


def _condition_digest(rows: pd.DataFrame) -> str:
    fields = [
        column for column in ("pair_id", "scenario_id", "seed", "episode_id") if column in rows
    ]
    payload = rows.loc[:, fields].astype(str).sort_values(fields).to_dict(orient="records")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def build_calibration_report(
    results: pd.DataFrame,
    *,
    reference_method: str = "base",
) -> dict[str, Any]:
    """Apply the preregistered gate to all valid Base validation episodes."""

    reference = results.loc[
        (results["source_policy"] == reference_method)
        & results["split"].astype(str).str.lower().eq("validation")
    ].copy()
    reference["_valid"] = _valid_mask(reference) if not reference.empty else False
    valid = reference.loc[reference["_valid"]]
    valid_count = len(valid)
    success_rate = float((valid["outcome"] == "GOAL_REACHED").mean()) if valid_count else None
    collision_timeout_rate = (
        float(valid["outcome"].isin(("COLLISION", "TIMEOUT")).mean()) if valid_count else None
    )
    distances = pd.to_numeric(valid["min_human_distance_m"], errors="coerce")
    finite_distance = np.isfinite(distances.to_numpy(dtype=np.float64))
    interaction = finite_distance & (
        distances.to_numpy(dtype=np.float64)
        < float(CALIBRATION_THRESHOLDS["interaction_distance_m"])
    )
    interaction_ratio = float(np.mean(interaction)) if valid_count else None
    interaction_family_count = int(valid.loc[interaction, "family"].nunique()) if valid_count else 0
    finite_distance_ratio = float(np.mean(finite_distance)) if valid_count else None

    checks = [
        _gate_check(
            name="success_rate",
            value=success_rate,
            minimum=CALIBRATION_THRESHOLDS["success_rate_min"],
            maximum=CALIBRATION_THRESHOLDS["success_rate_max"],
        ),
        _gate_check(
            name="collision_plus_timeout_rate",
            value=collision_timeout_rate,
            minimum=CALIBRATION_THRESHOLDS["collision_plus_timeout_rate_min"],
            maximum=CALIBRATION_THRESHOLDS["collision_plus_timeout_rate_max"],
        ),
        _gate_check(
            name="interaction_episode_ratio",
            value=interaction_ratio,
            minimum=CALIBRATION_THRESHOLDS["interaction_episode_ratio_min"],
        ),
        _gate_check(
            name="interaction_family_count",
            value=interaction_family_count,
            minimum=CALIBRATION_THRESHOLDS["interaction_family_count_min"],
        ),
    ]
    passed = bool(reference.shape[0] and valid_count and all(check["passed"] for check in checks))
    return {
        "schema_version": 1,
        "status": "accepted" if passed else "rejected",
        "passed": passed,
        "reference_method": reference_method,
        "split": "validation",
        "selection_policy": "all reference-method validation episodes; no family/seed filtering",
        "no_scenario_or_seed_filtering": True,
        "thresholds": CALIBRATION_THRESHOLDS,
        "counts": {
            "manifest_episode_count": len(reference),
            "valid_episode_count": valid_count,
            "excluded_episode_count": len(reference) - valid_count,
            "family_count": int(valid["family"].nunique()) if valid_count else 0,
            "scenario_count": int(valid["scenario_id"].nunique()) if valid_count else 0,
            "seed_count": int(valid["seed"].nunique()) if valid_count else 0,
            "interaction_episode_count": int(np.count_nonzero(interaction)),
            "interaction_family_count": interaction_family_count,
        },
        "metrics": {
            "success_rate": success_rate,
            "collision_plus_timeout_rate": collision_timeout_rate,
            "interaction_episode_ratio": interaction_ratio,
            "finite_human_distance_ratio": finite_distance_ratio,
        },
        "condition_sha256": _condition_digest(reference) if not reference.empty else None,
        "checks": checks,
    }


def _iter_tests(payload: Mapping[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    tests: list[tuple[str, dict[str, Any]]] = []
    binary = payload.get("binary_outcomes", {})
    if isinstance(binary, Mapping):
        for metric, analysis in binary.items():
            if isinstance(analysis, Mapping) and isinstance(analysis.get("mcnemar_exact"), dict):
                tests.append((f"mcnemar_{metric}", analysis["mcnemar_exact"]))
    continuous = payload.get("continuous_metrics", {})
    if isinstance(continuous, Mapping):
        for metric, analysis in continuous.items():
            if isinstance(analysis, Mapping) and isinstance(analysis.get("wilcoxon"), dict):
                tests.append((f"wilcoxon_{metric}", analysis["wilcoxon"]))
    return tests


def build_pairwise_statistics(
    results: pd.DataFrame,
    *,
    methods: Sequence[str],
    main_method: str = "pgrr",
    reference_method: str = "base",
    bootstrap_samples: int = 10_000,
    bootstrap_seed: int = 0,
    statistics: ModuleType | None = None,
) -> dict[str, Any]:
    """Compare every requested comparator with PGRR and apply one global Holm family."""

    if bootstrap_samples <= 0:
        raise ValueError("bootstrap_samples must be positive")
    module = statistics or _statistics_module()
    selected = results.loc[results["source_policy"].isin(methods)].copy()
    condition_evidence = validate_complete_condition_sets(
        selected,
        methods=methods,
        main_method=main_method,
        statistics=module,
    )
    comparators = [
        reference_method,
        *(m for m in methods if m not in {reference_method, main_method}),
    ]
    comparisons: dict[str, dict[str, Any]] = {}
    raw_pvalues: dict[str, float] = {}
    test_handles: dict[str, dict[str, Any]] = {}
    for comparator in comparators:
        stable_offset = int(hashlib.sha256(comparator.encode()).hexdigest()[:8], 16) % 1_000_000
        comparison = module.build_statistics(
            selected.loc[selected["source_policy"].isin((comparator, main_method))],
            reference_policy=comparator,
            treatment_policy=main_method,
            bootstrap_samples=bootstrap_samples,
            bootstrap_seed=bootstrap_seed + stable_offset,
        )
        comparison["direction"] = f"{main_method}_minus_{comparator}"
        comparisons[comparator] = comparison
        for test_name, test in _iter_tests(comparison):
            hypothesis = f"{comparator}::{test_name}"
            raw = float(test["pvalue_raw"])
            raw_pvalues[hypothesis] = raw
            test_handles[hypothesis] = test

    adjusted = module.holm_adjust(raw_pvalues) if raw_pvalues else {}
    hypotheses: list[dict[str, Any]] = []
    for hypothesis, raw in raw_pvalues.items():
        test = test_handles[hypothesis]
        local = test.get("pvalue_holm")
        test["pvalue_holm_within_comparison"] = local
        test["pvalue_holm"] = adjusted[hypothesis]
        comparator, test_name = hypothesis.split("::", maxsplit=1)
        hypotheses.append(
            {
                "hypothesis": hypothesis,
                "comparator": comparator,
                "test": test_name,
                "pvalue_raw": raw,
                "pvalue_holm_global": adjusted[hypothesis],
            }
        )
        comparisons[comparator]["multiple_comparison"] = {
            "method": "Holm",
            "scope": "all reported tests across every comparator versus the main method",
            "hypothesis_count_global": len(raw_pvalues),
        }

    return {
        "schema_version": 1,
        "status": "ok" if comparisons else "no_comparators",
        "main_method": main_method,
        "reference_method": reference_method,
        "methods": list(methods),
        "comparators": comparators,
        "analysis_policy": {
            "condition_selection": "all preregistered condition keys for each selected method",
            "scenario_or_seed_filtering": False,
            **condition_evidence,
        },
        "bootstrap": {"samples": bootstrap_samples, "seed_base": bootstrap_seed},
        "global_multiple_comparison": {
            "method": "Holm",
            "scope": "all McNemar and Wilcoxon tests across all comparator--main comparisons",
            "hypothesis_count": len(raw_pvalues),
            "hypotheses": hypotheses,
        },
        "comparisons": comparisons,
    }


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def write_outputs(
    *,
    results_path: Path,
    output_dir: Path,
    requested_methods: Sequence[str] | None = None,
    main_method: str = "pgrr",
    reference_method: str = "base",
    bootstrap_samples: int = 10_000,
    bootstrap_seed: int = 0,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    results = pd.read_parquet(results_path)
    _required_columns(results)
    methods = _method_order(
        results,
        requested_methods,
        main_method=main_method,
        reference_method=reference_method,
    )
    selected = results.loc[results["source_policy"].isin(methods)].copy()
    module = _statistics_module()
    validate_complete_condition_sets(
        selected,
        methods=methods,
        main_method=main_method,
        statistics=module,
    )
    summary = build_summary(selected, methods=methods)
    statistics = build_pairwise_statistics(
        selected,
        methods=methods,
        main_method=main_method,
        reference_method=reference_method,
        bootstrap_samples=bootstrap_samples,
        bootstrap_seed=bootstrap_seed,
        statistics=module,
    )
    calibration = build_calibration_report(selected, reference_method=reference_method)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.csv"
    temporary_summary = output_dir / "summary.csv.tmp"
    summary.to_csv(temporary_summary, index=False, lineterminator="\n")
    temporary_summary.replace(summary_path)
    _atomic_write_text(
        output_dir / "pairwise_statistics.json",
        json.dumps(statistics, indent=2, sort_keys=True, allow_nan=False) + "\n",
    )
    _atomic_write_text(
        output_dir / "calibration_report.json",
        json.dumps(calibration, indent=2, sort_keys=True, allow_nan=False) + "\n",
    )
    return summary, statistics, calibration


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for summary.csv and the two JSON reports; defaults beside --results.",
    )
    parser.add_argument(
        "--methods",
        nargs="+",
        default=None,
        help="Methods to compare. Conditions cannot be filtered and must match exactly.",
    )
    parser.add_argument("--main-method", default="pgrr")
    parser.add_argument("--reference-method", default="base")
    parser.add_argument("--bootstrap-samples", type=int, default=10_000)
    parser.add_argument("--bootstrap-seed", type=int, default=0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    output_dir = args.output_dir or args.results.parent
    write_outputs(
        results_path=args.results,
        output_dir=output_dir,
        requested_methods=args.methods,
        main_method=args.main_method,
        reference_method=args.reference_method,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed,
    )


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
