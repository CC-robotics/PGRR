#!/usr/bin/env python3
"""Generate publication figures exclusively from locked final artifacts.

The generator deliberately has no pilot-data fallback.  A paper build must fail
until both final artifacts exist and agree on one project commit.
"""

from __future__ import annotations

import argparse
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
from matplotlib.axes import Axes
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure
from matplotlib.patches import FancyArrowPatch, Polygon, Rectangle

ROOT = Path(__file__).resolve().parents[2]

BLUE = "#466B9F"
TEAL = "#16836B"
ORANGE = "#D97706"
INK = "#202124"
MID_GREY = "#667079"
LIGHT_GREY = "#EEF1F3"
GRID_GREY = "#D5DBDB"

ALGORITHM_FAILURES = {"COLLISION", "TIMEOUT", "PLANNER_FAILURE"}
EXCLUDED_OUTCOMES = {"SIMULATOR_FAILURE", "INVALID_RESET"}
VALID_OUTCOMES = {"GOAL_REACHED", *ALGORITHM_FAILURES, *EXCLUDED_OUTCOMES}

RESULT_ALIASES: dict[str, tuple[str, ...]] = {
    "episode_id": ("episode",),
    "scenario": ("family", "scenario_id"),
    "density": ("crowd_density",),
    "seed": ("random_seed",),
    "method": ("source_policy", "planner_id", "policy"),
    "project_commit": ("git_commit", "commit"),
    "outcome": ("terminal_outcome", "status"),
    "navigation_time_s": ("sim_duration_s", "duration_s", "time_s"),
    "spl": ("success_weighted_path_length",),
    "min_human_distance_m": ("minimum_human_distance_m", "min_human_distance"),
    "recovery_trigger_count": ("recovery_triggers", "trigger_count"),
    "recovery_success_rate": ("recovery_success",),
    "recovery_duration_s": ("mean_recovery_duration_s",),
    "intervention_ratio": ("recovery_intervention_ratio",),
    "emergency_stop_count": ("emergency_stops",),
}

SUMMARY_ALIASES: dict[str, tuple[str, ...]] = {
    "project_commit": ("git_commit", "commit"),
    "comparison": ("method_comparison",),
    "metric": ("metric_name",),
    "test": ("statistical_test", "test_name"),
    "estimate": ("difference", "effect_estimate"),
    "ci_low": ("ci_lower", "lower_95"),
    "ci_high": ("ci_upper", "upper_95"),
    "p_value": ("pvalue", "p_value_raw"),
    "p_value_holm": ("holm_p_value", "adjusted_p_value", "pvalue_holm"),
    "effect_size": ("effect",),
    "n_pairs": ("paired_n", "n"),
}

REQUIRED_RESULT_COLUMNS = (
    "episode_id",
    "scenario",
    "density",
    "seed",
    "method",
    "project_commit",
    "outcome",
    "navigation_time_s",
    "spl",
    "min_human_distance_m",
    "recovery_trigger_count",
    "recovery_success_rate",
    "recovery_duration_s",
    "intervention_ratio",
    "emergency_stop_count",
)

REQUIRED_SUMMARY_COLUMNS = (
    "project_commit",
    "comparison",
    "metric",
    "test",
    "estimate",
    "ci_low",
    "ci_high",
    "p_value",
    "p_value_holm",
    "effect_size",
    "n_pairs",
)

EXPECTED_MAIN_PAIR_COUNT = 24
EXPECTED_HIGH_DENSITY_PAIR_COUNT = 8

STATE_LABELS = {
    0: "NORMAL",
    1: "PENDING RECOVERY",
    2: "RECOVERY",
    3: "REJOIN",
    4: "EMERGENCY STOP",
    5: "FAILED",
    6: "SUCCEEDED",
}


class ArtifactError(RuntimeError):
    """Raised when final paper artifacts are absent, stale, or inconsistent."""


def _configure_matplotlib() -> None:
    """Apply a restrained IEEE-compatible vector style."""

    plt.rcParams.update(
        {
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "font.family": "sans-serif",
            "font.sans-serif": ["DejaVu Sans"],
            "font.size": 7.5,
            "axes.titlesize": 8.5,
            "axes.labelsize": 8.0,
            "xtick.labelsize": 7.0,
            "ytick.labelsize": 7.0,
            "legend.fontsize": 7.0,
            "axes.edgecolor": MID_GREY,
            "axes.linewidth": 0.7,
        }
    )


def _rename_aliases(
    frame: pd.DataFrame,
    aliases: dict[str, tuple[str, ...]],
) -> pd.DataFrame:
    result = frame.copy()
    renames: dict[str, str] = {}
    for canonical, candidates in aliases.items():
        if canonical in result.columns:
            continue
        # Collector outputs intentionally retain both detailed and aggregate
        # fields (for example ``scenario_id`` and ``family``).  Aliases are
        # therefore ordered by authority instead of being treated as an
        # ambiguity.
        match = next((candidate for candidate in candidates if candidate in result.columns), None)
        if match is not None:
            renames[match] = canonical
    return result.rename(columns=renames)


def _require_columns(frame: pd.DataFrame, required: Sequence[str], *, artifact: Path) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ArtifactError(f"{artifact} is missing required columns: {', '.join(missing)}")


def _normalise_results(frame: pd.DataFrame, *, artifact: Path) -> pd.DataFrame:
    if frame.empty:
        raise ArtifactError(f"{artifact} contains no episode results")
    result = _rename_aliases(frame, RESULT_ALIASES)
    # The collector preserves manifest detail columns as well as aggregate
    # columns.  Paper grouping is by scenario family and deployed policy, not
    # by the seed-bearing scenario identifier or the base planner ID.
    if "family" in result.columns:
        result["scenario"] = result["family"]
    if "source_policy" in result.columns:
        result["method"] = result["source_policy"]
    _require_columns(result, REQUIRED_RESULT_COLUMNS, artifact=artifact)

    for column in ("episode_id", "scenario", "density", "method", "project_commit"):
        result[column] = result[column].astype(str).str.strip()
        if result[column].eq("").any():
            raise ArtifactError(f"{artifact} contains an empty {column}")
    result["outcome"] = (
        result["outcome"].astype(str).str.strip().str.upper().str.replace(" ", "_", regex=False)
    )
    unexpected = sorted(set(result["outcome"]) - VALID_OUTCOMES)
    if unexpected:
        raise ArtifactError(f"{artifact} contains unsupported outcomes: {', '.join(unexpected)}")

    numeric_columns = (
        "seed",
        "navigation_time_s",
        "spl",
        "min_human_distance_m",
        "recovery_trigger_count",
        "recovery_success_rate",
        "recovery_duration_s",
        "intervention_ratio",
        "emergency_stop_count",
    )
    for column in numeric_columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    strictly_finite = (
        "seed",
        "navigation_time_s",
        "spl",
        "min_human_distance_m",
        "recovery_trigger_count",
        "intervention_ratio",
        "emergency_stop_count",
    )
    algorithm_rows = ~result["outcome"].isin(EXCLUDED_OUTCOMES)
    for column in strictly_finite:
        values = result.loc[algorithm_rows, column].to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ArtifactError(f"{artifact} contains non-finite {column} values in valid episodes")
    if (result.loc[algorithm_rows, "navigation_time_s"] < 0.0).any():
        raise ArtifactError(f"{artifact} contains negative navigation times")
    for column in ("spl", "recovery_success_rate", "intervention_ratio"):
        finite = result[column].dropna()
        if ((finite < 0.0) | (finite > 1.0)).any():
            raise ArtifactError(f"{artifact} contains {column} outside [0, 1]")

    commits = sorted(set(result["project_commit"]))
    if len(commits) != 1:
        raise ArtifactError(
            f"final results mix project commits ({', '.join(commits)}); freeze one revision"
        )

    pair_columns = ["scenario", "density", "seed"]
    duplicate = result.duplicated(subset=["method", *pair_columns], keep=False)
    if duplicate.any():
        example = result.loc[duplicate, ["method", *pair_columns]].iloc[0].to_dict()
        raise ArtifactError(f"duplicate method/episode result in {artifact}: {example}")
    episode_sets = {
        method: set(map(tuple, rows[pair_columns].itertuples(index=False, name=None)))
        for method, rows in result.groupby("method", sort=False)
    }

    def resolve_method(role: str, accepted: set[str]) -> str:
        matches = [
            method
            for method in episode_sets
            if method.lower().replace("_", " ").strip() in accepted
        ]
        if len(matches) != 1:
            raise ArtifactError(
                f"final results require exactly one {role} method; found {sorted(matches)}"
            )
        return matches[0]

    base_method = resolve_method(
        "base",
        {"base", "dwb", "classical dwb", "classical planner"},
    )
    bc_method = resolve_method(
        "BC",
        {"bc", "behavior cloning", "behaviour cloning"},
    )
    standard_method = resolve_method(
        "standard-recovery",
        {"standard", "standard recovery"},
    )
    heuristic_method = resolve_method(
        "heuristic-recovery",
        {"heuristic", "heuristic recovery"},
    )

    main_pairs = episode_sets[base_method]
    if episode_sets[bc_method] != main_pairs:
        raise ArtifactError("base and BC do not share the same paired 24-episode manifest")
    if len(main_pairs) != EXPECTED_MAIN_PAIR_COUNT:
        raise ArtifactError(
            "base/BC final manifest must contain exactly "
            f"{EXPECTED_MAIN_PAIR_COUNT} paired episodes; found {len(main_pairs)}"
        )

    standard_pairs = episode_sets[standard_method]
    if episode_sets[heuristic_method] != standard_pairs:
        raise ArtifactError(
            "standard and heuristic recovery do not share the same paired high-density subset"
        )
    if len(standard_pairs) != EXPECTED_HIGH_DENSITY_PAIR_COUNT:
        raise ArtifactError(
            "standard/heuristic final subset must contain exactly "
            f"{EXPECTED_HIGH_DENSITY_PAIR_COUNT} paired episodes; found {len(standard_pairs)}"
        )
    if not standard_pairs.issubset(main_pairs):
        raise ArtifactError("standard/heuristic episodes are not a subset of base/BC episodes")
    non_high = sorted({str(pair[1]) for pair in standard_pairs if str(pair[1]).lower() != "high"})
    if non_high:
        raise ArtifactError(
            "standard/heuristic subset contains non-high densities: " + ", ".join(non_high)
        )
    return result


def _normalise_summary(
    frame: pd.DataFrame,
    *,
    artifact: Path,
    expected_commit: str,
) -> pd.DataFrame:
    if frame.empty:
        raise ArtifactError(f"{artifact} contains no statistical comparisons")
    summary = _rename_aliases(frame, SUMMARY_ALIASES)
    if "row_type" in summary.columns:
        summary = summary.loc[
            summary["row_type"]
            .astype(str)
            .str.lower()
            .isin({"statistic", "paired_test", "comparison"})
        ].copy()
    _require_columns(summary, REQUIRED_SUMMARY_COLUMNS, artifact=artifact)
    if summary.empty:
        raise ArtifactError(f"{artifact} contains no paired statistical rows")

    for column in ("project_commit", "comparison", "metric", "test"):
        summary[column] = summary[column].astype(str).str.strip()
        if summary[column].eq("").any():
            raise ArtifactError(f"{artifact} contains an empty {column}")
    commits = sorted(set(summary["project_commit"]))
    if commits != [expected_commit]:
        raise ArtifactError(
            f"summary commit {commits} does not match final results commit {expected_commit}"
        )
    numeric_columns = (
        "estimate",
        "ci_low",
        "ci_high",
        "p_value",
        "p_value_holm",
        "effect_size",
        "n_pairs",
    )
    for column in numeric_columns:
        summary[column] = pd.to_numeric(summary[column], errors="coerce")
        if not np.isfinite(summary[column].to_numpy(dtype=float)).all():
            raise ArtifactError(f"{artifact} contains non-finite {column} values")
    for column in ("p_value", "p_value_holm"):
        if ((summary[column] < 0.0) | (summary[column] > 1.0)).any():
            raise ArtifactError(f"{artifact} contains {column} outside [0, 1]")
    if (summary["n_pairs"] <= 0).any():
        raise ArtifactError(f"{artifact} contains non-positive paired sample counts")
    if (summary["ci_low"] > summary["ci_high"]).any():
        raise ArtifactError(f"{artifact} contains reversed confidence intervals")
    return summary


def _close_enough(left: Any, right: Any) -> bool:
    try:
        return bool(np.isclose(float(left), float(right), rtol=1.0e-8, atol=1.0e-10))
    except (TypeError, ValueError):
        return False


def validate_statistics_json(path: Path, summary: pd.DataFrame) -> None:
    """Cross-check flattened CSV tests against the authoritative statistics JSON.

    ``statistics.json`` is optional for callers that only have the two declared
    paper inputs.  When it exists, however, disagreement is a hard error rather
    than silently preferring whichever artifact was read last.
    """

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ArtifactError(f"failed to read {path}: {error}") from error
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise ArtifactError(f"{path} does not contain a successful statistics payload")

    reference = str(payload.get("reference_policy", "")).strip().lower()
    treatment = str(payload.get("treatment_policy", "")).strip().lower()
    if reference not in {"base", "dwb"} or treatment not in {
        "bc",
        "behavior cloning",
        "behaviour cloning",
    }:
        raise ArtifactError(
            f"{path} compares {reference!r} with {treatment!r}, expected base with BC"
        )

    expected_rows: list[dict[str, Any]] = []
    binary = payload.get("binary_outcomes", {})
    if isinstance(binary, Mapping):
        for metric, analysis in binary.items():
            if not isinstance(analysis, Mapping):
                continue
            difference = analysis.get("difference_treatment_minus_reference")
            test = analysis.get("mcnemar_exact")
            if not isinstance(difference, Mapping) or not isinstance(test, Mapping):
                continue
            expected_rows.append(
                {
                    "metric": str(metric),
                    "test_prefix": "mcnemar",
                    "estimate": difference.get("estimate"),
                    "ci_low": difference.get("lower"),
                    "ci_high": difference.get("upper"),
                    "p_value": test.get("pvalue_raw"),
                    "p_value_holm": test.get("pvalue_holm"),
                    "effect_size": test.get("matched_odds_ratio_haldane"),
                    "n_pairs": analysis.get("pair_count"),
                }
            )
    continuous = payload.get("continuous_metrics", {})
    if isinstance(continuous, Mapping):
        for metric, analysis in continuous.items():
            if not isinstance(analysis, Mapping) or analysis.get("status") != "ok":
                continue
            difference = analysis.get("difference_treatment_minus_reference")
            test = analysis.get("wilcoxon")
            effect = analysis.get("effect_size")
            if (
                not isinstance(difference, Mapping)
                or not isinstance(test, Mapping)
                or not isinstance(effect, Mapping)
            ):
                continue
            expected_rows.append(
                {
                    "metric": str(metric),
                    "test_prefix": "wilcoxon",
                    "estimate": difference.get("estimate"),
                    "ci_low": difference.get("lower"),
                    "ci_high": difference.get("upper"),
                    "p_value": test.get("pvalue_raw"),
                    "p_value_holm": test.get("pvalue_holm"),
                    "effect_size": effect.get("rank_biserial_correlation"),
                    "n_pairs": analysis.get("pair_count"),
                }
            )
    if not expected_rows:
        raise ArtifactError(f"{path} contains no paired tests to cross-check")

    for expected in expected_rows:
        matches = summary.loc[
            summary["metric"].astype(str).str.lower().eq(expected["metric"].lower())
            & summary["test"].astype(str).str.lower().str.startswith(str(expected["test_prefix"]))
        ]
        if len(matches) != 1:
            raise ArtifactError(
                f"summary has {len(matches)} rows for statistics JSON metric {expected['metric']!r}"
            )
        row = matches.iloc[0]
        for column in (
            "estimate",
            "ci_low",
            "ci_high",
            "p_value",
            "p_value_holm",
            "effect_size",
            "n_pairs",
        ):
            if not _close_enough(row[column], expected[column]):
                raise ArtifactError(
                    f"{path} and summary disagree for {expected['metric']}.{column}: "
                    f"{expected[column]} vs {row[column]}"
                )


def load_final_artifacts(
    results_path: Path,
    summary_path: Path,
    statistics_path: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load and validate the two locked final artifacts.

    No file beneath ``outputs/pilot`` is consulted under any circumstance.
    """

    missing = [str(path) for path in (results_path, summary_path) if not path.is_file()]
    if missing:
        raise ArtifactError(
            "missing locked final artifact(s): "
            + ", ".join(missing)
            + ". No pilot fallback is permitted."
        )
    try:
        results = pd.read_parquet(results_path)
    except Exception as error:  # pragma: no cover - backend details vary
        raise ArtifactError(f"failed to read {results_path}: {error}") from error
    try:
        summary = pd.read_csv(summary_path)
    except Exception as error:
        raise ArtifactError(f"failed to read {summary_path}: {error}") from error
    results = _normalise_results(results, artifact=results_path)
    commit = str(results["project_commit"].iloc[0])
    summary = _normalise_summary(summary, artifact=summary_path, expected_commit=commit)
    if statistics_path is not None and statistics_path.is_file():
        validate_statistics_json(statistics_path, summary)
    return results, summary


def _method_order(methods: Sequence[str]) -> list[str]:
    def priority(method: str) -> tuple[int, str]:
        key = method.lower().replace("_", " ")
        if key in {"base", "dwb", "classical dwb", "classical planner"}:
            return (0, key)
        if "standard" in key:
            return (1, key)
        if "heuristic" in key:
            return (2, key)
        if key in {"bc", "behavior cloning", "behaviour cloning"}:
            return (3, key)
        if "dagger" in key or "full hierarchy" in key or key in {"ours", "selected"}:
            return (4, key)
        if "oracle" in key:
            return (5, key)
        return (3, key)

    return sorted(set(map(str, methods)), key=priority)


def display_method(method: str) -> str:
    key = method.lower().replace("_", " ").strip()
    names = {
        "base": "DWB",
        "dwb": "DWB",
        "classical dwb": "DWB",
        "standard": "Standard",
        "standard recovery": "Standard",
        "heuristic": "Heuristic",
        "heuristic recovery": "Heuristic",
        "bc": "PGRR",
        "behavior cloning": "PGRR",
        "behaviour cloning": "PGRR",
        "dagger": "PGRR",
        "bc recovery": "PGRR",
        "full hierarchy": "PGRR",
        "ours": "PGRR",
        "selected": "PGRR",
        "oracle": "Oracle",
    }
    return names.get(key, method.replace("_", " "))


def _select_central_methods(methods: Sequence[str]) -> tuple[str, str]:
    ordered = _method_order(methods)
    reference = next(
        (
            method
            for method in ordered
            if method.lower().replace("_", " ") in {"base", "dwb", "classical dwb"}
        ),
        ordered[0],
    )
    proposed = next(
        (
            method
            for method in reversed(ordered)
            if "dagger" in method.lower()
            or "full" in method.lower()
            or method.lower() in {"ours", "selected", "bc"}
        ),
        ordered[-1],
    )
    if proposed == reference:
        proposed = ordered[-1]
    return reference, proposed


def _valid_rows(results: pd.DataFrame) -> pd.DataFrame:
    return results.loc[~results["outcome"].isin(EXCLUDED_OUTCOMES)].copy()


def _save_pdf(figure: Figure, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        output,
        bbox_inches="tight",
        metadata={"CreationDate": None, "ModDate": None, "Creator": "PGRR final artifact"},
    )
    plt.close(figure)


def _box(
    axis: Axes,
    xy: tuple[float, float],
    width: float,
    height: float,
    label: str,
    *,
    facecolor: str = LIGHT_GREY,
    edgecolor: str = BLUE,
    linewidth: float = 1.0,
) -> Rectangle:
    patch = Rectangle(
        xy,
        width,
        height,
        facecolor=facecolor,
        edgecolor=edgecolor,
        linewidth=linewidth,
        joinstyle="round",
        zorder=3,
    )
    axis.add_patch(patch)
    axis.text(
        xy[0] + width / 2.0,
        xy[1] + height / 2.0,
        label,
        ha="center",
        va="center",
        fontsize=7.2,
        color=INK,
        zorder=4,
    )
    return patch


def _arrow(
    axis: Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    label: str | None = None,
    color: str = MID_GREY,
    connectionstyle: str = "arc3",
    label_offset_y: float = 0.025,
) -> None:
    arrow = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=8,
        linewidth=0.9,
        color=color,
        connectionstyle=connectionstyle,
        shrinkA=1.5,
        shrinkB=1.5,
        zorder=2,
    )
    axis.add_patch(arrow)
    if label:
        midpoint = (
            (start[0] + end[0]) / 2.0,
            (start[1] + end[1]) / 2.0 + label_offset_y,
        )
        axis.text(*midpoint, label, ha="center", va="bottom", fontsize=6.5, color=MID_GREY)


def architecture_figure(output: Path) -> None:
    """Draw the embodied closed loop and the privileged training boundary."""

    figure, axis = plt.subplots(figsize=(7.05, 2.55), constrained_layout=True)
    axis.set_xlim(0.0, 1.0)
    axis.set_ylim(0.0, 1.0)
    axis.axis("off")

    axis.add_patch(
        Rectangle(
            (0.01, 0.46),
            0.98,
            0.49,
            facecolor="#FAFBFC",
            edgecolor=GRID_GREY,
            linewidth=0.8,
            zorder=0,
        )
    )
    axis.text(0.025, 0.86, "DEPLOYMENT: OBSERVABLE CLOSED LOOP", fontsize=8.5, color=INK)
    axis.add_patch(
        Rectangle(
            (0.09, 0.04),
            0.57,
            0.31,
            facecolor="#FAFBFC",
            edgecolor=GRID_GREY,
            linewidth=0.9,
            linestyle="--",
            zorder=0,
        )
    )
    axis.text(0.105, 0.30, "TRAINING ONLY", fontsize=8.5, color=INK)

    _box(axis, (0.025, 0.61), 0.13, 0.17, "Dynamic world\n+ robot", facecolor="#E8EEF6")
    _box(axis, (0.175, 0.61), 0.14, 0.17, "5-frame LiDAR\npath + goal + state")

    diamond_center = (0.39, 0.695)
    diamond = Polygon(
        [
            (diamond_center[0], diamond_center[1] + 0.095),
            (diamond_center[0] + 0.065, diamond_center[1]),
            (diamond_center[0], diamond_center[1] - 0.095),
            (diamond_center[0] - 0.065, diamond_center[1]),
        ],
        closed=True,
        facecolor="#FFF1DC",
        edgecolor=ORANGE,
        linewidth=1.0,
        zorder=3,
    )
    axis.add_patch(diamond)
    axis.text(
        *diamond_center,
        "Failure\ntrigger?",
        ha="center",
        va="center",
        fontsize=7.2,
        color=INK,
        zorder=4,
    )
    _box(
        axis,
        (0.49, 0.61),
        0.13,
        0.17,
        "PGRR policy\n25 masked actions",
        facecolor="#DFF2ED",
        edgecolor=TEAL,
        linewidth=1.2,
    )
    _box(axis, (0.655, 0.61), 0.12, 0.17, "Goal mux\ntemporary / original")
    _box(axis, (0.81, 0.61), 0.15, 0.17, "Classical Nav2\nDWB + global path")

    _arrow(axis, (0.155, 0.695), (0.175, 0.695))
    _arrow(axis, (0.315, 0.695), (0.325, 0.695))
    _arrow(axis, (0.455, 0.695), (0.49, 0.695))
    _arrow(axis, (0.62, 0.695), (0.655, 0.695), color=TEAL)
    _arrow(axis, (0.775, 0.695), (0.81, 0.695))
    _arrow(
        axis,
        (0.885, 0.79),
        (0.09, 0.79),
        label="velocity command and environment feedback",
        color=TEAL,
        connectionstyle="arc3,rad=0.12",
    )
    _arrow(
        axis,
        (0.39, 0.59),
        (0.81, 0.59),
        label="no failure: original goal",
        connectionstyle="arc3,rad=-0.14",
        label_offset_y=-0.055,
    )

    _box(axis, (0.115, 0.10), 0.12, 0.12, "Privileged\nsimulator state")
    _box(axis, (0.285, 0.10), 0.13, 0.12, "Short-horizon\nplanning expert")
    _box(axis, (0.465, 0.10), 0.14, 0.12, "BC + DAgger\naggregated states")
    _arrow(axis, (0.235, 0.16), (0.285, 0.16), label="truth")
    _arrow(axis, (0.415, 0.16), (0.465, 0.16), label="actions + costs")
    _arrow(
        axis,
        (0.605, 0.16),
        (0.555, 0.60),
        label="export policy",
        color=TEAL,
        connectionstyle="arc3,rad=-0.12",
    )
    _arrow(
        axis,
        (0.095, 0.61),
        (0.175, 0.22),
        label="training rollouts",
        connectionstyle="arc3,rad=0.08",
    )
    _save_pdf(figure, output)


def _action_label(action_id: int) -> str:
    if 0 <= action_id < 21:
        radii = (0.6, 1.0, 1.4)
        angles = (-90, -60, -30, 0, 30, 60, 90)
        return f"SG {radii[action_id // 7]:.1f} m, {angles[action_id % 7]:+d}°"
    return {21: "WAIT", 22: "BACKUP", 23: "REPLAN", 24: "CONTINUE"}.get(
        action_id,
        f"ACTION {action_id}",
    )


def action_space_expert_figure(output: Path) -> None:
    """Visualise the exact fixed action set and a declared schematic mask."""

    radii = (0.6, 1.0, 1.4)
    angles = (-90, -60, -30, 0, 30, 60, 90)
    candidates: list[tuple[int, float, float]] = []
    for radius in radii:
        for angle_degrees in angles:
            angle = math.radians(angle_degrees)
            candidates.append((len(candidates), radius * math.cos(angle), radius * math.sin(angle)))

    # A vertical pedestrian crossing is deliberately schematic.  The mask is
    # computed geometrically here only to explain the interface; it is not an
    # episode result or a claim about a particular rollout.
    pedestrian_x = 0.92
    masked = {
        action_id
        for action_id, x_value, y_value in candidates
        if abs(x_value - pedestrian_x) < 0.27 and -0.95 <= y_value <= 0.95
    }
    valid_candidates = [item for item in candidates if item[0] not in masked]
    selected = min(valid_candidates, key=lambda item: (abs(item[2] - 0.45), -item[1]))[0]

    figure, axes = plt.subplots(
        1,
        2,
        figsize=(7.05, 2.65),
        gridspec_kw={"width_ratios": [1.2, 0.8]},
        constrained_layout=True,
    )
    axis = axes[0]
    for radius in radii:
        axis.add_patch(
            plt.Circle(
                (0.0, 0.0),
                radius,
                fill=False,
                color=GRID_GREY,
                linewidth=0.7,
                linestyle="--",
            )
        )
    for action_id, x_value, y_value in candidates:
        axis.plot([0.0, x_value], [0.0, y_value], color=BLUE, alpha=0.13, linewidth=0.5)
        if action_id in masked:
            axis.scatter(
                [x_value],
                [y_value],
                marker="x",
                color=ORANGE,
                linewidth=1.0,
                s=24,
                zorder=4,
            )
        else:
            axis.scatter(
                [x_value],
                [y_value],
                color=TEAL if action_id == selected else BLUE,
                edgecolor="white",
                linewidth=0.35,
                s=32 if action_id == selected else 18,
                marker="*" if action_id == selected else "o",
                zorder=4,
            )
        axis.text(x_value, y_value + 0.055, str(action_id), ha="center", fontsize=5.2, color=INK)
    pedestrian_y = np.linspace(-1.25, 1.25, 20)
    axis.plot(
        np.full_like(pedestrian_y, pedestrian_x),
        pedestrian_y,
        color=ORANGE,
        linewidth=1.1,
        linestyle="--",
    )
    axis.add_patch(
        FancyArrowPatch(
            (pedestrian_x, -0.95),
            (pedestrian_x, 0.95),
            arrowstyle="-|>",
            mutation_scale=8,
            color=ORANGE,
            linewidth=1.0,
        )
    )
    axis.scatter([pedestrian_x], [-1.05], color=ORANGE, s=28, zorder=5)
    axis.scatter([0.0], [0.0], marker=">", color=TEAL, s=55, zorder=5)
    axis.annotate(
        "schematic 3 s\npedestrian prediction",
        (pedestrian_x, 0.82),
        xytext=(1.12, 1.12),
        arrowprops={"arrowstyle": "-", "color": ORANGE, "linewidth": 0.7},
        color=ORANGE,
        fontsize=6.2,
        ha="left",
    )
    axis.set_aspect("equal")
    axis.set_xlim(-0.15, 1.60)
    axis.set_ylim(-1.58, 1.58)
    axis.set_xlabel("Robot-frame $x$ [m]")
    axis.set_ylabel("Robot-frame $y$ [m]")
    axis.set_title("(a) Temporary subgoals", loc="left", fontweight="bold")
    axis.grid(color=GRID_GREY, linewidth=0.45)
    axis.set_axisbelow(True)

    legend_axis = axes[1]
    legend_axis.axis("off")
    legend_axis.set_xlim(0.0, 1.0)
    legend_axis.set_ylim(0.0, 1.0)
    legend_axis.set_title("(b) Special actions and expert", loc="left", fontweight="bold")
    legend_axis.text(
        0.02,
        0.91,
        "SCHEMATIC — NOT AN EXPERIMENTAL RESULT",
        fontsize=6.4,
        color=ORANGE,
        fontweight="bold",
    )
    special_actions = ((21, "WAIT"), (22, "BACKUP"), (23, "REPLAN"), (24, "CONTINUE"))
    for index, (action_id, label) in enumerate(special_actions):
        x_value = 0.02 + 0.49 * (index % 2)
        y_value = 0.73 - 0.17 * (index // 2)
        _box(
            legend_axis,
            (x_value, y_value),
            0.44,
            0.11,
            f"{action_id}: {label}",
            facecolor="#FAFBFC",
            edgecolor=BLUE,
            linewidth=0.8,
        )
    legend_axis.text(
        0.02,
        0.47,
        r"$r \in \{0.6,1.0,1.4\}$ m; "
        r"$\theta \in \{-90,-60,\ldots,90\}^{\circ}$",
        fontsize=6.8,
        color=INK,
        va="top",
    )
    legend_axis.text(
        0.02,
        0.385,
        "3.0 s rollout per valid action\nDifferential-drive tracking + predicted pedestrians",
        fontsize=6.4,
        color=INK,
        va="top",
        linespacing=1.15,
    )
    legend_axis.text(
        0.02,
        0.27,
        r"$J = w_cJ_c + w_pJ_p + w_sJ_s + w_rJ_r$"
        "\n+ path length, smoothness, time, and switch costs",
        fontsize=6.6,
        color=INK,
        va="top",
        linespacing=1.1,
    )
    for y_value, color, marker, label in (
        (0.115, BLUE, "o", "valid candidate"),
        (0.062, ORANGE, "x", "masked candidate"),
        (0.009, TEAL, "*", "minimum-cost valid action"),
    ):
        legend_axis.scatter([0.05], [y_value], color=color, marker=marker, s=22)
        legend_axis.text(0.10, y_value, label, va="center", fontsize=6.1)
    _save_pdf(figure, output)


def _preferred_order(values: Sequence[str], preferred: Sequence[str]) -> list[str]:
    normalised = {value.lower().replace("_", " "): value for value in map(str, values)}
    ordered = [normalised[key] for key in preferred if key in normalised]
    return ordered + sorted(set(map(str, values)) - set(ordered))


def _flow_arrow(
    axis: Axes,
    start: tuple[float, float],
    end: tuple[float, float],
    color: str,
    *,
    linewidth: float = 1.2,
) -> None:
    axis.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=7,
            color=color,
            linewidth=linewidth,
        )
    )


def _draw_scenario_schematic(axis: Axes, scenario: str) -> None:
    key = scenario.lower().replace("_", " ")
    wall = {"facecolor": GRID_GREY, "edgecolor": MID_GREY, "linewidth": 0.5}
    if key == "head on corridor":
        axis.add_patch(Rectangle((-1.8, -1.0), 3.6, 0.35, **wall))
        axis.add_patch(Rectangle((-1.8, 0.65), 3.6, 0.35, **wall))
        _flow_arrow(axis, (-1.45, -0.16), (1.25, -0.16), BLUE)
        _flow_arrow(axis, (1.40, 0.18), (-1.20, 0.18), ORANGE)
    elif key == "doorway bottleneck":
        axis.add_patch(Rectangle((-0.22, -1.0), 0.44, 0.65, **wall))
        axis.add_patch(Rectangle((-0.22, 0.35), 0.44, 0.65, **wall))
        _flow_arrow(axis, (-1.55, 0.0), (1.35, 0.0), BLUE)
        _flow_arrow(axis, (1.30, 0.18), (-0.85, 0.18), ORANGE)
    elif key == "crossing flow":
        _flow_arrow(axis, (-1.55, -0.15), (1.45, -0.15), BLUE)
        _flow_arrow(axis, (0.15, -0.90), (0.15, 0.85), ORANGE)
    elif key == "blind corner":
        axis.add_patch(Rectangle((-1.8, 0.28), 1.95, 0.72, **wall))
        axis.add_patch(Rectangle((0.15, 0.28), 0.45, 0.72, **wall))
        _flow_arrow(axis, (-1.45, -0.15), (0.78, -0.15), BLUE)
        _flow_arrow(axis, (0.95, 0.82), (0.95, -0.45), ORANGE)
    elif key == "group blocking":
        _flow_arrow(axis, (-1.55, 0.0), (1.45, 0.0), BLUE)
        for x_value, y_value in ((0.15, -0.30), (0.38, 0.0), (0.10, 0.30), (0.63, 0.27)):
            axis.scatter([x_value], [y_value], color=ORANGE, s=18)
    elif key == "overtaking":
        _flow_arrow(axis, (-1.55, -0.22), (1.45, -0.22), BLUE)
        _flow_arrow(axis, (-0.35, 0.20), (0.65, 0.20), ORANGE)
    elif key == "opposite streams":
        _flow_arrow(axis, (-1.55, -0.30), (1.45, -0.30), BLUE)
        for y_value in (-0.05, 0.25, 0.55):
            _flow_arrow(axis, (1.35, y_value), (-1.25, y_value), ORANGE, linewidth=0.9)
    elif key == "temporary blockage":
        _flow_arrow(axis, (-1.55, 0.0), (1.45, 0.0), BLUE)
        for y_value in (-0.32, 0.0, 0.32):
            axis.scatter([0.30], [y_value], color=ORANGE, s=20)
        axis.text(0.43, 0.50, "temporary stop", color=ORANGE, fontsize=5.7, ha="center")
    else:
        _flow_arrow(axis, (-1.55, -0.15), (1.45, -0.15), BLUE)
        _flow_arrow(axis, (0.15, -0.90), (0.15, 0.85), ORANGE)
    axis.set_xlim(-1.8, 1.8)
    axis.set_ylim(-1.0, 1.0)
    axis.set_aspect("equal")
    axis.set_xticks([])
    axis.set_yticks([])
    axis.set_title(scenario.replace("_", " "), fontsize=7.1, pad=2.0)
    for spine in axis.spines.values():
        spine.set_color(GRID_GREY)
        spine.set_linewidth(0.6)


def scenario_montage_figure(results: pd.DataFrame, output: Path) -> None:
    scenarios = _preferred_order(
        results["scenario"].unique(),
        (
            "head on corridor",
            "doorway bottleneck",
            "crossing flow",
            "blind corner",
            "group blocking",
            "overtaking",
            "opposite streams",
            "temporary blockage",
        ),
    )
    if not scenarios:
        raise ArtifactError("final results contain no scenario families for the montage")
    columns = min(4, len(scenarios))
    rows = math.ceil(len(scenarios) / columns)
    figure, axes = plt.subplots(
        rows,
        columns,
        figsize=(7.05, 1.55 * rows + 0.35),
        constrained_layout=True,
        squeeze=False,
    )
    for axis, scenario in zip(axes.flat, scenarios, strict=False):
        _draw_scenario_schematic(axis, scenario)
    for axis in list(axes.flat)[len(scenarios) :]:
        axis.axis("off")
    figure.suptitle(
        "Final scenario families — schematic geometry (not outcome data)",
        fontsize=8.5,
        fontweight="bold",
    )
    figure.text(
        0.5,
        0.005,
        "Blue: robot route; orange: pedestrian flow or temporary occupancy; gray: static boundary",
        ha="center",
        fontsize=6.4,
        color=MID_GREY,
    )
    _save_pdf(figure, output)


def outcome_density_figure(results: pd.DataFrame, output: Path) -> None:
    valid = _valid_rows(results)
    reference, proposed = _select_central_methods(valid["method"].unique())
    central = valid.loc[valid["method"].isin({reference, proposed})].copy()
    scenarios = _preferred_order(
        central["scenario"].unique(),
        (
            "head on corridor",
            "doorway bottleneck",
            "crossing flow",
            "blind corner",
            "group blocking",
            "overtaking",
            "opposite streams",
            "temporary blockage",
        ),
    )
    methods = [reference, proposed]
    matrix = np.zeros((len(scenarios), len(methods)), dtype=float)
    counts = np.zeros_like(matrix, dtype=int)
    successes = np.zeros_like(matrix, dtype=int)
    for row_index, scenario in enumerate(scenarios):
        for column_index, method in enumerate(methods):
            selected = central.loc[
                (central["scenario"] == scenario) & (central["method"] == method)
            ]
            counts[row_index, column_index] = len(selected)
            successes[row_index, column_index] = int((selected["outcome"] == "GOAL_REACHED").sum())
            matrix[row_index, column_index] = (
                successes[row_index, column_index] / len(selected) if len(selected) else np.nan
            )

    figure, axes = plt.subplots(
        1,
        2,
        figsize=(7.05, max(2.65, 0.32 * len(scenarios) + 1.25)),
        gridspec_kw={"width_ratios": [0.9, 1.45]},
        constrained_layout=True,
    )
    color_map = LinearSegmentedColormap.from_list("success", [LIGHT_GREY, TEAL])
    image = axes[0].imshow(matrix, vmin=0.0, vmax=1.0, cmap=color_map, aspect="auto")
    axes[0].set_title("(a) Success by scenario", loc="left", fontweight="bold")
    axes[0].set_xticks(np.arange(len(methods)), [display_method(method) for method in methods])
    axes[0].set_yticks(np.arange(len(scenarios)), [item.replace("_", " ") for item in scenarios])
    for row_index in range(len(scenarios)):
        for column_index in range(len(methods)):
            if counts[row_index, column_index]:
                axes[0].text(
                    column_index,
                    row_index,
                    f"{100.0 * matrix[row_index, column_index]:.0f}%\n"
                    f"({successes[row_index, column_index]}/{counts[row_index, column_index]})",
                    ha="center",
                    va="center",
                    color="white" if matrix[row_index, column_index] >= 0.60 else INK,
                    fontsize=6.8,
                )
    colorbar = figure.colorbar(image, ax=axes[0], fraction=0.055, pad=0.04)
    colorbar.set_label("Success rate")
    colorbar.set_ticks([0.0, 0.5, 1.0])

    densities = _preferred_order(
        central["density"].unique(),
        ("low", "medium", "high"),
    )
    x_positions = np.arange(len(densities) * len(methods), dtype=float)
    bar_labels: list[str] = []
    bottoms = np.zeros_like(x_positions)
    categories = (
        ("Goal", "GOAL_REACHED", TEAL),
        ("Collision", "COLLISION", ORANGE),
        ("Other failure", "OTHER", BLUE),
    )
    for category_label, category, color in categories:
        fractions: list[float] = []
        for density in densities:
            for method in methods:
                selected = central.loc[
                    (central["density"] == density) & (central["method"] == method)
                ]
                if category == "OTHER":
                    count = int(selected["outcome"].isin({"TIMEOUT", "PLANNER_FAILURE"}).sum())
                else:
                    count = int((selected["outcome"] == category).sum())
                fractions.append(count / len(selected) if len(selected) else 0.0)
                if category_label == "Goal":
                    short_method = display_method(method).replace("Triggered ", "")
                    bar_labels.append(f"{str(density).title()}\n{short_method}")
        values = np.asarray(fractions, dtype=float)
        axes[1].bar(
            x_positions,
            values,
            bottom=bottoms,
            width=0.74,
            color=color,
            edgecolor="white",
            linewidth=0.5,
            label=category_label,
        )
        bottoms += values
    axes[1].set_title("(b) Terminal outcomes by density", loc="left", fontweight="bold")
    axes[1].set_ylabel("Fraction of valid episodes")
    axes[1].set_ylim(0.0, 1.0)
    axes[1].set_xticks(x_positions, bar_labels)
    axes[1].grid(axis="y", color=GRID_GREY, linewidth=0.6)
    axes[1].set_axisbelow(True)
    axes[1].legend(
        frameon=False,
        ncol=3,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.23),
    )
    _save_pdf(figure, output)


def _bootstrap_median(values: np.ndarray, *, seed: int) -> tuple[float, float, float]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return (np.nan, np.nan, np.nan)
    estimate = float(np.median(finite))
    if finite.size == 1:
        return (estimate, estimate, estimate)
    generator = np.random.default_rng(seed)
    indices = generator.integers(0, finite.size, size=(4_000, finite.size))
    distribution = np.median(finite[indices], axis=1)
    lower, upper = np.quantile(distribution, [0.025, 0.975])
    return (estimate, float(lower), float(upper))


def safety_efficiency_figure(results: pd.DataFrame, output: Path) -> None:
    valid = _valid_rows(results)
    reference, proposed = _select_central_methods(valid["method"].unique())
    methods = _method_order(valid["method"].unique())
    core_methods = [
        method
        for method in methods
        if method.lower().replace("_", " ").strip()
        in {
            "base",
            "dwb",
            "classical dwb",
            "classical planner",
            "standard",
            "standard recovery",
            "heuristic",
            "heuristic recovery",
            "bc",
            "behavior cloning",
            "behaviour cloning",
        }
    ]
    pair_columns = ["scenario", "density", "seed"]
    pair_sets = {
        method: set(
            map(
                tuple,
                valid.loc[valid["method"] == method, pair_columns].itertuples(
                    index=False,
                    name=None,
                ),
            )
        )
        for method in core_methods
    }
    common_pairs = set.intersection(*(pair_sets[method] for method in core_methods))
    if not common_pairs:
        raise ArtifactError("no common valid high-density subset for safety-efficiency figure")
    valid = valid.loc[
        valid[pair_columns].apply(tuple, axis=1).isin(common_pairs)
        & valid["method"].isin(core_methods)
    ]
    methods = _method_order(valid["method"].unique())
    figure, axis = plt.subplots(figsize=(3.45, 2.65), constrained_layout=True)
    markers = ("o", "s", "^", "D", "P", "X", "v")
    plotted = 0
    for method_index, method in enumerate(methods):
        selected = valid.loc[valid["method"] == method]
        successful = selected.loc[selected["outcome"] == "GOAL_REACHED"]
        if successful.empty:
            continue
        time = _bootstrap_median(
            successful["navigation_time_s"].to_numpy(dtype=float),
            seed=1300 + method_index,
        )
        clearance = _bootstrap_median(
            selected["min_human_distance_m"].to_numpy(dtype=float),
            seed=2300 + method_index,
        )
        if method == reference:
            color = ORANGE
        elif method == proposed:
            color = TEAL
        else:
            color = BLUE
        success_rate = float((selected["outcome"] == "GOAL_REACHED").mean())
        axis.errorbar(
            time[0],
            clearance[0],
            xerr=np.asarray([[time[0] - time[1]], [time[2] - time[0]]]),
            yerr=np.asarray([[clearance[0] - clearance[1]], [clearance[2] - clearance[0]]]),
            fmt=markers[method_index % len(markers)],
            markersize=6.5,
            markerfacecolor=color,
            markeredgecolor="white",
            markeredgewidth=0.6,
            ecolor=color,
            elinewidth=0.9,
            capsize=2.0,
            zorder=3,
        )
        align_right = method_index >= max(1, len(methods) // 2)
        vertical_offset = -11 if method == proposed else 5
        axis.annotate(
            f"{display_method(method)} ({100.0 * success_rate:.0f}%)",
            (time[0], clearance[0]),
            xytext=(-5 if align_right else 5, vertical_offset),
            textcoords="offset points",
            fontsize=6.8,
            color=INK,
            ha="right" if align_right else "left",
        )
        plotted += 1
    if plotted == 0:
        raise ArtifactError("no method has a successful episode for the safety-efficiency plot")
    axis.set_xlabel("Median time on successful episodes [s]")
    axis.set_ylabel("Median minimum human distance [m]")
    axis.margins(x=0.13, y=0.16)
    axis.grid(color=GRID_GREY, linewidth=0.6)
    axis.set_axisbelow(True)
    axis.text(
        0.02,
        0.98,
        f"Same {len(common_pairs)} high-density episodes\n"
        "Error bars: bootstrap 95% CI; labels: success",
        ha="left",
        va="top",
        transform=axis.transAxes,
        fontsize=6.2,
        color=MID_GREY,
    )
    _save_pdf(figure, output)


def _state_code(value: Any) -> int:
    if isinstance(value, str):
        key = value.upper().replace("_", " ").strip()
        inverse = {label: code for code, label in STATE_LABELS.items()}
        if key in inverse:
            return inverse[key]
    try:
        code = int(value)
    except (TypeError, ValueError) as error:
        raise ArtifactError(f"invalid recovery state {value!r} in runtime JSONL") from error
    if code not in STATE_LABELS:
        raise ArtifactError(f"unknown recovery state {code} in runtime JSONL")
    return code


def _finite_vector(value: Any, minimum_length: int) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < minimum_length:
        return None
    try:
        vector = [float(component) for component in value]
    except (TypeError, ValueError):
        return None
    return vector if np.isfinite(vector).all() else None


def _runtime_pose(row: Mapping[str, Any]) -> list[float] | None:
    privileged = row.get("privileged")
    if isinstance(privileged, Mapping):
        pose = _finite_vector(privileged.get("robot_pose"), 3)
        if pose is not None:
            return pose
    return _finite_vector(row.get("robot_pose"), 3)


def _runtime_humans(row: Mapping[str, Any]) -> list[list[float]]:
    privileged = row.get("privileged")
    values = privileged.get("human_positions") if isinstance(privileged, Mapping) else None
    if values is None:
        values = row.get("human_positions")
    if not isinstance(values, (list, tuple)):
        return []
    humans: list[list[float]] = []
    for value in values:
        position = _finite_vector(value, 2)
        if position is not None:
            humans.append(position)
    return humans


def _runtime_path(row: Mapping[str, Any]) -> list[list[float]]:
    values = row.get("global_path")
    if not isinstance(values, (list, tuple)):
        return []
    path: list[list[float]] = []
    for value in values:
        position = _finite_vector(value, 2)
        if position is not None:
            path.append(position)
    return path


def _read_runtime_stream(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ArtifactError(f"invalid JSON at {path}:{line_number}: {error}") from error
                if not isinstance(raw, dict):
                    raise ArtifactError(f"runtime record at {path}:{line_number} is not an object")
                try:
                    timestamp = float(raw["timestamp"])
                except (KeyError, TypeError, ValueError) as error:
                    raise ArtifactError(
                        f"runtime record at {path}:{line_number} has no numeric timestamp"
                    ) from error
                if not math.isfinite(timestamp):
                    raise ArtifactError(f"non-finite timestamp at {path}:{line_number}")
                records.append(
                    {
                        "timestamp": timestamp,
                        "robot_pose": _runtime_pose(raw),
                        "humans": _runtime_humans(raw),
                        "global_path": _runtime_path(raw),
                        "goal": _finite_vector(raw.get("goal"), 2),
                        "failure_score": raw.get("failure_score"),
                        "distance_to_goal": raw.get("distance_to_goal"),
                        "recovery_state": _state_code(raw.get("recovery_state", 0)),
                        "recovery_action": int(raw.get("recovery_action", 24)),
                    }
                )
    except OSError as error:
        raise ArtifactError(f"failed to read runtime JSONL {path}: {error}") from error
    if len(records) < 3:
        raise ArtifactError(f"runtime JSONL {path} contains fewer than three frames")
    timestamps = np.asarray([record["timestamp"] for record in records], dtype=float)
    if np.any(np.diff(timestamps) <= 0.0):
        raise ArtifactError(f"runtime JSONL {path} is not strictly ordered by timestamp")
    if any(record["robot_pose"] is None for record in records):
        raise ArtifactError(f"runtime JSONL {path} has a frame without an actual robot pose")
    return records


def _load_json_object(path: Path, purpose: str) -> dict[str, Any]:
    if not path.is_file():
        raise ArtifactError(f"missing {purpose} for selected runtime episode: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ArtifactError(f"failed to read {purpose} {path}: {error}") from error
    if not isinstance(payload, dict):
        raise ArtifactError(f"{purpose} {path} is not a JSON object")
    return payload


def load_representative_runtime(
    results: pd.DataFrame,
    raw_dir: Path,
) -> tuple[pd.Series[Any], list[dict[str, Any]], Path]:
    """Select and load a provenance-linked BC recovery episode."""

    if not raw_dir.is_dir():
        raise ArtifactError(f"raw runtime directory does not exist: {raw_dir}")
    bc_methods = [
        method
        for method in results["method"].unique()
        if str(method).lower().replace("_", " ").strip()
        in {"bc", "behavior cloning", "behaviour cloning"}
    ]
    if len(bc_methods) != 1:
        raise ArtifactError(f"cannot identify one BC method for runtime sequence: {bc_methods}")
    candidates = results.loc[
        (results["method"] == bc_methods[0])
        & (results["recovery_trigger_count"] > 0)
        & ~results["outcome"].isin(EXCLUDED_OUTCOMES)
    ].copy()
    if candidates.empty:
        raise ArtifactError("final BC results contain no episode with a recovery trigger")
    candidates["_is_success"] = (candidates["outcome"] == "GOAL_REACHED").astype(int)
    candidates["_density_rank"] = (
        candidates["density"].astype(str).str.lower().map({"low": 0, "medium": 1, "high": 2})
    )
    for column in ("progress_m", "recovery_success_rate", "min_human_distance_m"):
        if column not in candidates:
            candidates[column] = np.nan
        candidates[column] = pd.to_numeric(candidates[column], errors="coerce")
    successful_candidates = candidates.loc[candidates["_is_success"] == 1]
    if not successful_candidates.empty:
        candidates = successful_candidates.sort_values(
            [
                "_density_rank",
                "recovery_success_rate",
                "recovery_trigger_count",
                "min_human_distance_m",
                "progress_m",
                "episode_id",
            ],
            ascending=[False, False, False, True, False, True],
            na_position="last",
            kind="stable",
        )
    else:
        # The fallback is explicitly the greatest measured progress, as stated
        # in the paper caption; it is never re-labelled as a successful case.
        candidates = candidates.sort_values(
            ["progress_m", "recovery_trigger_count", "episode_id"],
            ascending=[False, False, True],
            na_position="last",
            kind="stable",
        )

    selected: pd.Series[Any] | None = None
    stream_path: Path | None = None
    missing_paths: list[Path] = []
    for _, row in candidates.iterrows():
        episode_id = str(row["episode_id"])
        if Path(episode_id).name != episode_id:
            raise ArtifactError(f"unsafe episode_id in final results: {episode_id!r}")
        candidate_path = raw_dir / f"{episode_id}.jsonl"
        if candidate_path.is_file():
            selected = row
            stream_path = candidate_path
            break
        missing_paths.append(candidate_path)
    if selected is None or stream_path is None:
        examples = ", ".join(str(path) for path in missing_paths[:3])
        raise ArtifactError(
            "no raw JSONL exists for any triggered BC final episode; expected files such as "
            + examples
        )

    metadata_path = stream_path.with_suffix(".metadata.json")
    outcome_path = stream_path.with_suffix(".outcome.json")
    metadata = _load_json_object(metadata_path, "runtime metadata")
    outcome = _load_json_object(outcome_path, "runtime outcome")
    episode_id = str(selected["episode_id"])
    sidecar_episode_ids = {
        str(metadata.get("episode_id")),
        str(outcome.get("episode_id")),
    }
    if sidecar_episode_ids != {episode_id}:
        raise ArtifactError(f"runtime sidecars do not identify selected episode {episode_id}")
    if str(metadata.get("project_commit")) != str(selected["project_commit"]):
        raise ArtifactError(
            f"runtime metadata commit does not match final result for episode {episode_id}"
        )
    if str(outcome.get("outcome", "")).upper() != str(selected["outcome"]):
        raise ArtifactError(f"runtime outcome does not match final result for episode {episode_id}")
    return selected, _read_runtime_stream(stream_path), stream_path


def _first_recovery_index(records: Sequence[Mapping[str, Any]]) -> int:
    for index, record in enumerate(records):
        state = int(record["recovery_state"])
        action = int(record["recovery_action"])
        if state in {1, 2, 3, 4} or action != 24:
            if index == 0 or index == len(records) - 1:
                raise ArtifactError(
                    "recovery event is not temporally separated from runtime endpoints"
                )
            return index
    raise ArtifactError("selected triggered episode has no recovery state/action in its raw JSONL")


def runtime_sequence_figure(
    selected: pd.Series[Any],
    records: Sequence[Mapping[str, Any]],
    stream_path: Path,
    output: Path,
) -> None:
    recovery_index = _first_recovery_index(records)
    indices = (0, recovery_index, len(records) - 1)
    frame_labels = ("Start", "First recovery", "Terminal")
    frames = [records[index] for index in indices]
    trajectory = np.asarray([record["robot_pose"][:2] for record in records], dtype=float)
    local_half_width = 3.0

    figure, axes = plt.subplots(1, 3, figsize=(7.05, 2.65), constrained_layout=True)
    for panel_index, (axis, frame, record_index, label) in enumerate(
        zip(axes, frames, indices, frame_labels, strict=True)
    ):
        path = np.asarray(frame["global_path"], dtype=float)
        if path.size:
            axis.plot(
                path[:, 0],
                path[:, 1],
                color=BLUE,
                linestyle="--",
                linewidth=1.0,
                label="global path" if panel_index == 0 else None,
            )
        axis.plot(
            trajectory[: record_index + 1, 0],
            trajectory[: record_index + 1, 1],
            color=TEAL,
            linewidth=1.15,
            label="actual trajectory" if panel_index == 0 else None,
        )
        humans = np.asarray(frame["humans"], dtype=float)
        if humans.size:
            axis.scatter(
                humans[:, 0],
                humans[:, 1],
                color=ORANGE,
                edgecolor="white",
                linewidth=0.35,
                s=25,
                label="logged humans" if panel_index == 0 else None,
                zorder=4,
            )
        pose = frame["robot_pose"]
        axis.scatter([pose[0]], [pose[1]], color=TEAL, s=28, zorder=5)
        heading_length = 0.30
        _flow_arrow(
            axis,
            (pose[0], pose[1]),
            (
                pose[0] + heading_length * math.cos(pose[2]),
                pose[1] + heading_length * math.sin(pose[2]),
            ),
            TEAL,
            linewidth=1.0,
        )
        goal = frame["goal"]
        if goal is not None:
            axis.scatter(
                [goal[0]],
                [goal[1]],
                marker="*",
                color=BLUE,
                s=38,
                label="goal" if panel_index == 0 else None,
                zorder=4,
            )
        state = STATE_LABELS[int(frame["recovery_state"])]
        action = _action_label(int(frame["recovery_action"]))
        axis.set_title(
            f"({chr(97 + panel_index)}) {label}: $t$={float(frame['timestamp']):.1f} s",
            loc="left",
            fontweight="bold",
        )
        axis.text(
            0.02,
            0.02,
            f"{state}\n{action}",
            transform=axis.transAxes,
            va="bottom",
            ha="left",
            fontsize=6.1,
            color=INK,
            bbox={"facecolor": "white", "edgecolor": GRID_GREY, "pad": 2.0, "alpha": 0.9},
        )
        axis.set_xlim(pose[0] - local_half_width, pose[0] + local_half_width)
        axis.set_ylim(pose[1] - local_half_width, pose[1] + local_half_width)
        axis.set_aspect("equal")
        axis.grid(color=GRID_GREY, linewidth=0.45)
        axis.set_xlabel("world $x$ [m]")
        if panel_index == 0:
            axis.set_ylabel("world $y$ [m]")
            axis.legend(frameon=False, loc="upper left", fontsize=5.8)
    successful = str(selected["outcome"]) == "GOAL_REACHED"
    evidence_note = (
        "successful triggered recovery"
        if successful
        else "unsuccessful episode shown only as measured interaction evidence"
    )
    figure.suptitle(
        f"Logged PGRR runtime sequence — {selected['scenario']} / {selected['density']} "
        f"({evidence_note})",
        fontsize=8.2,
        fontweight="bold",
    )
    figure.text(
        0.5,
        -0.01,
        f"Source: {stream_path.name}; each 6 m local view uses recorded timestamps, poses, "
        "humans, path, state, and action.",
        ha="center",
        fontsize=5.8,
        color=MID_GREY,
    )
    _save_pdf(figure, output)


def recovery_timeline_figure(
    selected: pd.Series[Any],
    records: Sequence[Mapping[str, Any]],
    output: Path,
) -> None:
    time = np.asarray([float(record["timestamp"]) for record in records], dtype=float)
    failure = pd.to_numeric(
        pd.Series([record["failure_score"] for record in records]), errors="coerce"
    ).to_numpy(dtype=float)
    distance = pd.to_numeric(
        pd.Series([record["distance_to_goal"] for record in records]), errors="coerce"
    ).to_numpy(dtype=float)
    if not np.isfinite(failure).all() or not np.isfinite(distance).all():
        raise ArtifactError("runtime JSONL lacks a finite failure score or goal distance timeline")
    states = np.asarray([int(record["recovery_state"]) for record in records], dtype=float)
    actions = np.asarray([int(record["recovery_action"]) for record in records], dtype=float)

    figure, axes = plt.subplots(3, 1, figsize=(7.05, 3.15), sharex=True, constrained_layout=True)
    axes[0].plot(time, failure, color=ORANGE, linewidth=1.0)
    axes[0].set_ylabel("Failure score")
    axes[1].plot(time, distance, color=BLUE, linewidth=1.0)
    axes[1].set_ylabel("Goal distance [m]")
    axes[2].step(time, states, where="post", color=TEAL, linewidth=1.0, label="state")
    action_axis = axes[2].twinx()
    action_axis.step(
        time,
        actions,
        where="post",
        color=BLUE,
        linewidth=0.7,
        alpha=0.75,
        label="action ID",
    )
    present_states = sorted(set(states.astype(int)))
    axes[2].set_yticks(present_states, [STATE_LABELS[state] for state in present_states])
    axes[2].set_ylabel("Recovery state")
    action_axis.set_ylabel("Action ID", color=BLUE)
    action_axis.tick_params(axis="y", colors=BLUE)
    axes[2].set_xlabel("Simulation time [s]")
    for axis in axes:
        axis.grid(axis="y", color=GRID_GREY, linewidth=0.55)
        axis.set_axisbelow(True)
    axes[0].set_title(
        f"Logged timeline: {selected['episode_id']} — {display_method(str(selected['method']))}",
        loc="left",
        fontweight="bold",
    )
    _save_pdf(figure, output)


def generate_figures(
    results_path: Path,
    summary_path: Path,
    output_dir: Path,
    raw_dir: Path = ROOT / "data/raw",
    statistics_path: Path | None = ROOT / "outputs/final/statistics.json",
) -> list[Path]:
    """Validate locked artifacts and generate the complete vector figure set."""

    _configure_matplotlib()
    results, _ = load_final_artifacts(results_path, summary_path, statistics_path)
    selected, runtime_records, stream_path = load_representative_runtime(results, raw_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = [
        output_dir / "system_architecture.pdf",
        output_dir / "action_space_expert.pdf",
        output_dir / "final_scenario_montage.pdf",
        output_dir / "final_outcomes_by_density.pdf",
        output_dir / "final_safety_efficiency.pdf",
        output_dir / "final_recovery_timeline.pdf",
        output_dir / "runtime_sequence.pdf",
    ]
    architecture_figure(outputs[0])
    action_space_expert_figure(outputs[1])
    scenario_montage_figure(results, outputs[2])
    outcome_density_figure(results, outputs[3])
    safety_efficiency_figure(results, outputs[4])
    recovery_timeline_figure(selected, runtime_records, outputs[5])
    runtime_sequence_figure(selected, runtime_records, stream_path, outputs[6])
    return outputs


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        type=Path,
        default=ROOT / "outputs/final/results.parquet",
        help="Locked episode-level results Parquet (default: outputs/final/results.parquet)",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=ROOT / "outputs/final/summary.csv",
        help="Locked statistical summary CSV (default: outputs/final/summary.csv)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "paper/figures",
        help="Destination for vector PDFs (default: paper/figures)",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=ROOT / "data/raw",
        help="Final episode JSONL directory used for logged runtime figures (default: data/raw)",
    )
    parser.add_argument(
        "--statistics-json",
        type=Path,
        default=ROOT / "outputs/final/statistics.json",
        help="Optional authoritative statistics JSON; cross-checked when present",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        outputs = generate_figures(
            args.results,
            args.summary,
            args.output_dir,
            args.raw_dir,
            args.statistics_json,
        )
    except (ArtifactError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
