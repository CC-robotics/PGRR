#!/usr/bin/env python3
"""Compute paired Base-versus-recovery statistics from final episode results."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import binomtest, rankdata, wilcoxon  # type: ignore[import-untyped]

EXCLUDED_OUTCOMES = frozenset({"SIMULATOR_FAILURE", "INVALID_RESET"})


def _native(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return number if math.isfinite(number) else None
    return str(value)


def _bootstrap_difference(
    reference: np.ndarray,
    treatment: np.ndarray,
    *,
    seed: int,
    samples: int,
    confidence: float = 0.95,
) -> dict[str, float | int]:
    if reference.shape != treatment.shape or reference.ndim != 1 or reference.size == 0:
        raise ValueError("bootstrap inputs must be non-empty paired vectors")
    if samples <= 0:
        raise ValueError("bootstrap_samples must be positive")
    differences = treatment - reference
    generator = np.random.default_rng(seed)
    indices = generator.integers(0, differences.size, size=(samples, differences.size))
    distribution = differences[indices].mean(axis=1)
    alpha = (1.0 - confidence) / 2.0
    lower, upper = np.quantile(distribution, (alpha, 1.0 - alpha))
    return {
        "estimate": float(np.mean(differences)),
        "lower": float(lower),
        "upper": float(upper),
        "confidence": confidence,
        "bootstrap_samples": samples,
    }


def _exact_mcnemar(reference: np.ndarray, treatment: np.ndarray) -> dict[str, float | int]:
    reference_only = int(np.sum((reference == 1) & (treatment == 0)))
    treatment_only = int(np.sum((reference == 0) & (treatment == 1)))
    discordant = reference_only + treatment_only
    pvalue = (
        1.0
        if discordant == 0
        else float(binomtest(min(reference_only, treatment_only), discordant, 0.5).pvalue)
    )
    return {
        "reference_only": reference_only,
        "treatment_only": treatment_only,
        "discordant_pairs": discordant,
        "pvalue_raw": pvalue,
        "matched_odds_ratio_haldane": (treatment_only + 0.5) / (reference_only + 0.5),
    }


def _paired_wilcoxon(reference: np.ndarray, treatment: np.ndarray) -> dict[str, float | int]:
    differences = treatment - reference
    nonzero = int(np.count_nonzero(differences))
    if nonzero == 0:
        return {"statistic": 0.0, "pvalue_raw": 1.0, "nonzero_pairs": 0}
    result = wilcoxon(
        treatment,
        reference,
        alternative="two-sided",
        zero_method="wilcox",
        method="auto",
    )
    return {
        "statistic": float(result.statistic),
        "pvalue_raw": float(result.pvalue),
        "nonzero_pairs": nonzero,
    }


def _effect_sizes(reference: np.ndarray, treatment: np.ndarray) -> dict[str, float | None]:
    differences = treatment - reference
    if differences.size > 1:
        deviation = float(np.std(differences, ddof=1))
        mean = float(np.mean(differences))
        cohen_dz = mean / deviation if deviation > 0.0 else (0.0 if mean == 0.0 else None)
    else:
        cohen_dz = None
    nonzero = differences[differences != 0.0]
    if nonzero.size == 0:
        rank_biserial = 0.0
    else:
        ranks = rankdata(np.abs(nonzero), method="average")
        denominator = float(np.sum(ranks))
        rank_biserial = float(
            (np.sum(ranks[nonzero > 0.0]) - np.sum(ranks[nonzero < 0.0])) / denominator
        )
    return {
        "cohen_dz": cohen_dz,
        "rank_biserial_correlation": rank_biserial,
    }


def holm_adjust(pvalues: dict[str, float]) -> dict[str, float]:
    """Return Holm step-down adjusted p-values, including tied/all-one inputs."""

    if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in pvalues.values()):
        raise ValueError("Holm inputs must be finite probabilities")
    ordered = sorted(pvalues.items(), key=lambda item: (item[1], item[0]))
    adjusted: dict[str, float] = {}
    running = 0.0
    total = len(ordered)
    for index, (name, pvalue) in enumerate(ordered):
        running = max(running, min(1.0, (total - index) * pvalue))
        adjusted[name] = running
    return adjusted


def _infer_replicate(episode_id: str) -> int:
    match = re.search(r"(?:^|_)r(?P<replicate>\d+)(?:_|$)", episode_id)
    return int(match.group("replicate")) if match is not None else 1


def _pairing_columns(results: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    working = results.copy()
    if "pair_id" in working.columns and working["pair_id"].notna().all():
        return working, ["pair_id"]
    required = [column for column in ("scenario_id", "seed") if column in working.columns]
    if "scenario_id" not in required:
        raise ValueError("results require pair_id or scenario_id for paired statistics")
    for optional in ("replicate", "repeat", "run_index"):
        if optional in working.columns and working[optional].notna().all():
            required.append(optional)
            return working, required
    working["_inferred_replicate"] = working["episode_id"].astype(str).map(_infer_replicate)
    required.append("_inferred_replicate")
    return working, required


def _pair_key_payload(columns: Sequence[str], key: tuple[object, ...]) -> dict[str, object]:
    return {column.lstrip("_"): _native(value) for column, value in zip(columns, key, strict=True)}


def _valid_flag(row: pd.Series) -> bool:
    if "included_in_algorithm_metrics" in row:
        return bool(row["included_in_algorithm_metrics"])
    return str(row.get("outcome")) not in EXCLUDED_OUTCOMES


def _build_pairs(
    results: pd.DataFrame,
    *,
    reference_policy: str,
    treatment_policy: str,
) -> tuple[
    list[tuple[dict[str, object], pd.Series, pd.Series]],
    list[dict[str, object]],
    list[str],
]:
    working, columns = _pairing_columns(results)
    selected = working[working["source_policy"].isin((reference_policy, treatment_policy))]
    pairs: list[tuple[dict[str, object], pd.Series, pd.Series]] = []
    excluded: list[dict[str, object]] = []
    grouper: str | list[str] = columns[0] if len(columns) == 1 else columns
    for raw_key, group in selected.groupby(grouper, dropna=False, sort=True):
        key = raw_key if isinstance(raw_key, tuple) else (raw_key,)
        key_payload = _pair_key_payload(columns, key)
        reasons: list[str] = []
        method_rows: dict[str, pd.Series] = {}
        for policy in (reference_policy, treatment_policy):
            rows = group[group["source_policy"] == policy]
            if len(rows) == 0:
                reasons.append(f"missing_{policy}")
            elif len(rows) > 1:
                raise ValueError(f"duplicate {policy} rows for pair {key_payload}")
            else:
                row = rows.iloc[0]
                method_rows[policy] = row
                if not _valid_flag(row):
                    reasons.append(f"{policy}_{row['outcome']}")
        if reasons:
            excluded.append({"pair": key_payload, "reasons": reasons})
        else:
            pairs.append(
                (key_payload, method_rows[reference_policy], method_rows[treatment_policy])
            )
    return pairs, excluded, [column.lstrip("_") for column in columns]


def _binary_analysis(
    pairs: Sequence[tuple[dict[str, object], pd.Series, pd.Series]],
    *,
    outcome: str,
    seed: int,
    samples: int,
) -> dict[str, Any]:
    reference = np.asarray([int(ref["outcome"] == outcome) for _, ref, _ in pairs], dtype=np.int8)
    treatment = np.asarray([int(test["outcome"] == outcome) for _, _, test in pairs], dtype=np.int8)
    result = {
        "pair_count": len(pairs),
        "reference_count": int(np.sum(reference)),
        "treatment_count": int(np.sum(treatment)),
        "reference_rate": float(np.mean(reference)),
        "treatment_rate": float(np.mean(treatment)),
        "difference_treatment_minus_reference": _bootstrap_difference(
            reference.astype(np.float64),
            treatment.astype(np.float64),
            seed=seed,
            samples=samples,
        ),
        "mcnemar_exact": _exact_mcnemar(reference, treatment),
    }
    return result


METRIC_SPECS: dict[str, tuple[str, str]] = {
    "successful_episode_duration_s": ("episode_duration_s", "joint_success"),
    "successful_path_length_m": ("path_length_m", "joint_success"),
    "spl": ("spl", "all_valid_pairs"),
    "min_human_distance_m": ("min_human_distance_m", "all_valid_pairs"),
    "personal_space_violation_ratio": (
        "personal_space_violation_ratio",
        "all_valid_pairs",
    ),
    "discomfort_time_s": ("discomfort_time_s", "all_valid_pairs"),
    "emergency_stop_count": ("emergency_stop_count", "all_valid_pairs"),
    "recovery_trigger_count": ("recovery_trigger_count", "all_valid_pairs"),
    "intervention_ratio": ("intervention_ratio", "all_valid_pairs"),
    "mean_abs_angular_jerk_rad_s3": (
        "mean_abs_angular_jerk_rad_s3",
        "all_valid_pairs",
    ),
}


def _continuous_analysis(
    pairs: Sequence[tuple[dict[str, object], pd.Series, pd.Series]],
    *,
    column: str,
    population: str,
    seed: int,
    samples: int,
) -> dict[str, Any]:
    values: list[tuple[float, float]] = []
    for _, reference_row, treatment_row in pairs:
        if population == "joint_success" and (
            reference_row["outcome"] != "GOAL_REACHED" or treatment_row["outcome"] != "GOAL_REACHED"
        ):
            continue
        reference = pd.to_numeric(pd.Series([reference_row.get(column)]), errors="coerce").iloc[0]
        treatment = pd.to_numeric(pd.Series([treatment_row.get(column)]), errors="coerce").iloc[0]
        if (
            pd.notna(reference)
            and pd.notna(treatment)
            and math.isfinite(float(reference))
            and math.isfinite(float(treatment))
        ):
            values.append((float(reference), float(treatment)))
    if not values:
        return {
            "population": population,
            "pair_count": 0,
            "reference_mean": None,
            "treatment_mean": None,
            "difference_treatment_minus_reference": None,
            "wilcoxon": None,
            "effect_size": None,
            "status": "insufficient_finite_pairs",
        }
    reference_array = np.asarray([value[0] for value in values], dtype=np.float64)
    treatment_array = np.asarray([value[1] for value in values], dtype=np.float64)
    return {
        "population": population,
        "pair_count": len(values),
        "reference_mean": float(np.mean(reference_array)),
        "treatment_mean": float(np.mean(treatment_array)),
        "reference_median": float(np.median(reference_array)),
        "treatment_median": float(np.median(treatment_array)),
        "difference_treatment_minus_reference": _bootstrap_difference(
            reference_array,
            treatment_array,
            seed=seed,
            samples=samples,
        ),
        "wilcoxon": _paired_wilcoxon(reference_array, treatment_array),
        "effect_size": _effect_sizes(reference_array, treatment_array),
        "status": "ok",
    }


def _exclusion_counts(results: pd.DataFrame) -> dict[str, dict[str, int]]:
    payload: dict[str, dict[str, int]] = {}
    for policy, group in results.groupby("source_policy", dropna=False, sort=True):
        counts: dict[str, int] = {}
        for outcome in sorted(EXCLUDED_OUTCOMES):
            attempt_column = f"{outcome.lower()}_attempt_count"
            if attempt_column in group.columns:
                counts[outcome.lower()] = int(
                    pd.to_numeric(group[attempt_column], errors="coerce").fillna(0).sum()
                )
            else:
                counts[outcome.lower()] = int((group["outcome"] == outcome).sum())
        payload[str(policy)] = counts
    return payload


def build_statistics(
    results: pd.DataFrame,
    *,
    reference_policy: str = "base",
    treatment_policy: str = "bc",
    bootstrap_samples: int = 10_000,
    bootstrap_seed: int = 0,
) -> dict[str, Any]:
    """Build robust paired statistics and one family-wide Holm correction."""

    required = {"episode_id", "source_policy", "outcome"}
    missing = sorted(required - set(results.columns))
    if missing:
        raise ValueError(f"results are missing required columns: {', '.join(missing)}")
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap_samples must be positive")
    pairs, excluded_pairs, pairing_columns = _build_pairs(
        results,
        reference_policy=reference_policy,
        treatment_policy=treatment_policy,
    )
    if not pairs:
        return {
            "schema_version": 1,
            "reference_policy": reference_policy,
            "treatment_policy": treatment_policy,
            "manifest_episode_count": len(results),
            "pairing_columns": pairing_columns,
            "valid_pair_count": 0,
            "excluded_pair_count": len(excluded_pairs),
            "excluded_pairs": excluded_pairs,
            "excluded_episode_counts": _exclusion_counts(results),
            "binary_outcomes": {},
            "continuous_metrics": {},
            "multiple_comparison": {"method": "Holm", "hypothesis_count": 0},
            "status": "no_complete_valid_pairs",
        }

    binary: dict[str, dict[str, Any]] = {}
    for index, outcome in enumerate(("GOAL_REACHED", "COLLISION", "TIMEOUT")):
        binary[outcome.lower()] = _binary_analysis(
            pairs,
            outcome=outcome,
            seed=bootstrap_seed + index,
            samples=bootstrap_samples,
        )
    continuous = {
        name: _continuous_analysis(
            pairs,
            column=column,
            population=population,
            seed=bootstrap_seed + 10 + index,
            samples=bootstrap_samples,
        )
        for index, (name, (column, population)) in enumerate(METRIC_SPECS.items())
    }

    tests: dict[str, dict[str, Any]] = {}
    pvalues: dict[str, float] = {}
    for outcome, analysis in binary.items():
        test = analysis["mcnemar_exact"]
        name = f"mcnemar_{outcome}"
        tests[name] = test
        pvalues[name] = float(test["pvalue_raw"])
    for metric, analysis in continuous.items():
        test = analysis.get("wilcoxon")
        if isinstance(test, dict):
            name = f"wilcoxon_{metric}"
            tests[name] = test
            pvalues[name] = float(test["pvalue_raw"])
    adjusted = holm_adjust(pvalues)
    for name, test in tests.items():
        test["pvalue_holm"] = adjusted[name]

    return {
        "schema_version": 1,
        "reference_policy": reference_policy,
        "treatment_policy": treatment_policy,
        "manifest_episode_count": len(results),
        "pairing_columns": pairing_columns,
        "valid_pair_count": len(pairs),
        "excluded_pair_count": len(excluded_pairs),
        "excluded_pairs": excluded_pairs,
        "excluded_episode_counts": _exclusion_counts(results),
        "bootstrap": {
            "samples": bootstrap_samples,
            "seed": bootstrap_seed,
            "confidence": 0.95,
            "resampling_unit": "episode_pair",
        },
        "binary_outcomes": binary,
        "continuous_metrics": continuous,
        "multiple_comparison": {
            "method": "Holm",
            "hypothesis_count": len(pvalues),
            "scope": "all reported McNemar and Wilcoxon tests",
        },
        "status": "ok",
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("outputs/final/results.parquet"))
    parser.add_argument("--output", type=Path, default=Path("outputs/final/statistics.json"))
    parser.add_argument("--reference-policy", default="base")
    parser.add_argument("--treatment-policy", default="bc")
    parser.add_argument("--bootstrap-samples", type=int, default=10_000)
    parser.add_argument("--bootstrap-seed", type=int, default=0)
    args = parser.parse_args(argv)
    results = pd.read_parquet(args.results)
    payload = build_statistics(
        results,
        reference_policy=args.reference_policy,
        treatment_policy=args.treatment_policy,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
