#!/usr/bin/env python3
"""Generate vector figures for the locked five-method moderate benchmark."""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.ticker import PercentFormatter

try:
    from moderate_artifacts import (
        ALGORITHM_OUTCOMES,
        DENSITY_ORDER,
        EXCLUDED_OUTCOMES,
        ROOT,
        ModerateArtifactError,
        bootstrap_median,
        display_method,
        load_moderate_artifacts,
        method_order,
        wilson_interval,
    )
except ModuleNotFoundError:  # Imported as a namespace module by pytest.
    from scripts.paper.moderate_artifacts import (
        ALGORITHM_OUTCOMES,
        DENSITY_ORDER,
        EXCLUDED_OUTCOMES,
        ROOT,
        ModerateArtifactError,
        bootstrap_median,
        display_method,
        load_moderate_artifacts,
        method_order,
        wilson_interval,
    )

# Three functional color groups follow the Robot/Embodied publication profile:
# neutral gray for classical controls, blue for learned/structured baselines,
# and orange for the proposed method or adverse terminal events.  Marker shape,
# hatching, and direct labels duplicate color so printouts remain accessible.
INK = "#1B1F23"
MID_GREY = "#59636B"
LIGHT_GREY = "#F2F4F5"
GRID_GREY = "#D7DDE1"
METHOD_COLORS = {
    "base": "#4D5963",
    "standard": "#8A959E",
    "heuristic": "#356E9F",
    "bc_uniform": "#78A9CC",
    "pgrr": "#D55E00",
}
METHOD_COLOR_GROUPS = {
    "base": "neutral",
    "standard": "neutral",
    "heuristic": "blue",
    "bc_uniform": "blue",
    "pgrr": "orange",
}
OUTCOME_COLORS = {
    "GOAL_REACHED": "#356E9F",
    "COLLISION": "#D55E00",
    "TIMEOUT": "#78A9CC",
    "PLANNER_FAILURE": "#7A7F85",
}
OUTCOME_COLOR_GROUPS = {
    "GOAL_REACHED": "blue",
    "COLLISION": "orange",
    "TIMEOUT": "blue",
    "PLANNER_FAILURE": "neutral",
}
OUTCOME_HATCHES = {
    "GOAL_REACHED": "",
    "COLLISION": "////",
    "TIMEOUT": "....",
    "PLANNER_FAILURE": "xx",
}
OUTCOME_LABELS = {
    "GOAL_REACHED": "Goal reached",
    "COLLISION": "Collision",
    "TIMEOUT": "Timeout",
    "PLANNER_FAILURE": "Planner failure",
}
MARKERS = {
    "base": "o",
    "standard": "s",
    "heuristic": "^",
    "bc_uniform": "D",
    "pgrr": "P",
}

DOUBLE_COLUMN_WIDTH_IN = 7.16


def _configure_matplotlib() -> None:
    plt.rcParams.update(
        {
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Liberation Sans", "DejaVu Sans"],
            "font.size": 8.6,
            "axes.titlesize": 9.2,
            "axes.titleweight": "semibold",
            "axes.labelsize": 8.8,
            "xtick.labelsize": 7.8,
            "ytick.labelsize": 7.8,
            "legend.fontsize": 7.5,
            "axes.edgecolor": MID_GREY,
            "axes.linewidth": 0.75,
            "axes.facecolor": "white",
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
            "hatch.linewidth": 0.65,
            "legend.frameon": False,
        }
    )


def _save_pdf(figure: Figure, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        output,
        bbox_inches="tight",
        metadata={
            "CreationDate": None,
            "ModDate": None,
            "Creator": "PGRR moderate artifact generator",
        },
    )
    plt.close(figure)


def _valid(results: pd.DataFrame) -> pd.DataFrame:
    return results.loc[~results["outcome"].isin(EXCLUDED_OUTCOMES)].copy()


def outcome_and_density_figure(results: pd.DataFrame, output: Path) -> None:
    """Plot all terminal outcomes and density-wise success with uncertainty."""

    valid = _valid(results)
    methods = method_order(valid["source_policy"].unique())
    figure, axes = plt.subplots(
        1,
        2,
        figsize=(DOUBLE_COLUMN_WIDTH_IN, 3.12),
        gridspec_kw={"width_ratios": [0.94, 1.06]},
        constrained_layout=True,
    )

    x_positions = np.arange(len(methods), dtype=float)
    bottom = np.zeros(len(methods), dtype=float)
    totals = np.asarray(
        [int((valid["source_policy"] == method).sum()) for method in methods],
        dtype=int,
    )
    for outcome in ALGORITHM_OUTCOMES:
        counts = np.asarray(
            [
                int(((valid["source_policy"] == method) & (valid["outcome"] == outcome)).sum())
                for method in methods
            ],
            dtype=int,
        )
        rates = np.divide(counts, totals, out=np.zeros_like(bottom), where=totals > 0)
        bars = axes[0].bar(
            x_positions,
            rates,
            bottom=bottom,
            width=0.68,
            color=OUTCOME_COLORS[outcome],
            edgecolor="white" if not OUTCOME_HATCHES[outcome] else INK,
            linewidth=0.45,
            hatch=OUTCOME_HATCHES[outcome],
            label=OUTCOME_LABELS[outcome],
        )
        for bar, count, rate in zip(bars, counts, rates, strict=True):
            if count and rate >= 0.085:
                axes[0].text(
                    bar.get_x() + bar.get_width() / 2.0,
                    bar.get_y() + bar.get_height() / 2.0,
                    str(count),
                    ha="center",
                    va="center",
                    fontsize=7.0,
                    color="white" if outcome in {"GOAL_REACHED", "COLLISION"} else INK,
                    fontweight="semibold",
                )
        bottom += rates
    axes[0].set_title("(a) Terminal outcomes", loc="left")
    axes[0].set_ylabel("Fraction of valid episodes")
    axes[0].set_ylim(0.0, 1.02)
    axes[0].set_xticks(
        x_positions,
        [
            f"{display_method(method)}\n$n={total}$"
            for method, total in zip(methods, totals, strict=True)
        ],
    )
    axes[0].yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    axes[0].grid(axis="y", color=GRID_GREY, linewidth=0.55)
    axes[0].set_axisbelow(True)
    axes[0].legend(
        ncol=2,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.20),
        handlelength=1.55,
        columnspacing=1.2,
    )

    densities = [density for density in DENSITY_ORDER if density in set(valid["density"])]
    density_x = np.arange(len(densities), dtype=float)
    offsets = np.linspace(-0.24, 0.24, num=len(methods))
    point_counts: dict[tuple[str, str], int] = {}
    for method, offset in zip(methods, offsets, strict=True):
        estimates: list[float] = []
        lower: list[float] = []
        upper: list[float] = []
        for density in densities:
            selected = valid.loc[(valid["source_policy"] == method) & (valid["density"] == density)]
            total = len(selected)
            point_counts[(method, density)] = total
            successes = int((selected["outcome"] == "GOAL_REACHED").sum())
            estimate, low, high = wilson_interval(successes, total)
            estimates.append(estimate)
            lower.append(estimate - low)
            upper.append(high - estimate)
        axes[1].errorbar(
            density_x + offset,
            estimates,
            yerr=np.asarray([lower, upper]),
            color=METHOD_COLORS[method],
            linestyle="none",
            marker=MARKERS[method],
            markerfacecolor=METHOD_COLORS[method] if method == "pgrr" else "white",
            markeredgecolor=METHOD_COLORS[method],
            markeredgewidth=1.0,
            markersize=5.5,
            elinewidth=0.9,
            capsize=2.3,
            label=display_method(method),
            zorder=3,
        )
    axes[1].set_title("(b) Goal rate by crowd density", loc="left")
    axes[1].set_ylabel("Goal-reaching rate (Wilson 95% CI)")
    axes[1].set_ylim(-0.03, 1.03)
    axes[1].set_xticks(density_x, [density.title() for density in densities])
    axes[1].yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    axes[1].grid(axis="y", color=GRID_GREY, linewidth=0.55)
    axes[1].set_axisbelow(True)
    axes[1].legend(
        ncol=3,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.20),
        columnspacing=1.0,
        handletextpad=0.35,
    )
    counts = sorted(set(point_counts.values()))
    count_note = (
        f"n={counts[0]} per point"
        if len(counts) == 1
        else f"n range: {counts[0]}--{counts[-1]} per point"
    )
    figure.text(
        0.5,
        -0.015,
        "Numbers in bars are episode counts; timeout and planner failure remain explicit. "
        f"Density panel: {count_note}. Infrastructure/reset exclusions are not algorithm outcomes.",
        ha="center",
        va="top",
        fontsize=7.0,
        color=MID_GREY,
    )
    _save_pdf(figure, output)


def family_success_figure(results: pd.DataFrame, output: Path) -> None:
    """Show family-wise successes as exact counts for all five methods."""

    valid = _valid(results)
    methods = method_order(valid["source_policy"].unique())
    preferred = (
        "head_on_corridor",
        "doorway_bottleneck",
        "crossing_flow",
        "blind_corner",
        "group_blocking",
        "overtaking",
        "opposite_streams",
        "temporary_blockage",
    )
    available = set(valid["family"].astype(str))
    families = [family for family in preferred if family in available]
    families.extend(sorted(available - set(families)))
    matrix = np.full((len(families), len(methods)), np.nan, dtype=float)
    counts = np.zeros_like(matrix, dtype=int)
    successes = np.zeros_like(matrix, dtype=int)
    for row_index, family in enumerate(families):
        for column_index, method in enumerate(methods):
            selected = valid.loc[(valid["family"] == family) & (valid["source_policy"] == method)]
            counts[row_index, column_index] = len(selected)
            successes[row_index, column_index] = int((selected["outcome"] == "GOAL_REACHED").sum())
            if len(selected):
                matrix[row_index, column_index] = successes[row_index, column_index] / len(selected)

    figure, axis = plt.subplots(
        figsize=(DOUBLE_COLUMN_WIDTH_IN, max(2.55, 0.31 * len(families) + 0.85)),
    )
    figure.subplots_adjust(left=0.18, right=0.91, top=0.87, bottom=0.20)
    color_map = matplotlib.colors.LinearSegmentedColormap.from_list(
        "moderate_success",
        [LIGHT_GREY, "#BCD7EA", "#356E9F"],
    )
    image = axis.imshow(matrix, vmin=0.0, vmax=1.0, cmap=color_map, aspect="auto")
    for row_index in range(len(families)):
        for column_index in range(len(methods)):
            if counts[row_index, column_index]:
                axis.text(
                    column_index,
                    row_index,
                    f"{successes[row_index, column_index]}/{counts[row_index, column_index]}",
                    ha="center",
                    va="center",
                    fontsize=7.5,
                    color="white" if matrix[row_index, column_index] >= 0.68 else INK,
                    fontweight="semibold",
                )
    axis.set_xticks(np.arange(len(methods)), [display_method(method) for method in methods])
    axis.set_yticks(
        np.arange(len(families)),
        [family.replace("_", " ") for family in families],
    )
    axis.tick_params(length=0)
    axis.set_title("Goal-reaching episodes by stress family (all densities)", loc="left")
    colorbar = figure.colorbar(image, ax=axis, fraction=0.026, pad=0.025)
    colorbar.set_label("Goal-reaching rate")
    colorbar.ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    figure.text(
        0.5,
        0.002,
        "Each cell reports goals / valid episodes; no family, seed, or terminal "
        "outcome is filtered.",
        ha="center",
        fontsize=7.1,
        color=MID_GREY,
    )
    _save_pdf(figure, output)


def paired_effect_figure(statistics: Mapping[str, object], output: Path) -> None:
    """Draw paired PGRR-minus-baseline binary effects with bootstrap intervals."""

    comparisons = statistics["comparisons"]
    assert isinstance(comparisons, Mapping)
    comparators = list(statistics["comparators"])
    endpoints = (
        ("goal_reached", "Goal reached", "o"),
        ("collision", "Collision", "X"),
        ("timeout", "Timeout", "s"),
    )
    figure, axes = plt.subplots(
        1,
        3,
        figsize=(DOUBLE_COLUMN_WIDTH_IN, 2.55),
        sharey=True,
        constrained_layout=True,
    )
    y_positions = np.arange(len(comparators), dtype=float)
    for axis, (endpoint, label, marker) in zip(axes, endpoints, strict=True):
        for y_position, comparator in zip(y_positions, comparators, strict=True):
            comparison = comparisons[comparator]
            assert isinstance(comparison, Mapping)
            binary = comparison["binary_outcomes"]
            assert isinstance(binary, Mapping)
            analysis = binary[endpoint]
            assert isinstance(analysis, Mapping)
            interval = analysis["difference_treatment_minus_reference"]
            test = analysis["mcnemar_exact"]
            assert isinstance(interval, Mapping) and isinstance(test, Mapping)
            estimate = 100.0 * float(interval["estimate"])
            lower = 100.0 * float(interval["lower"])
            upper = 100.0 * float(interval["upper"])
            axis.errorbar(
                estimate,
                y_position,
                xerr=np.asarray([[estimate - lower], [upper - estimate]]),
                fmt=marker,
                color=METHOD_COLORS[comparator],
                markerfacecolor="white",
                markeredgewidth=1.0,
                markersize=5.3,
                elinewidth=1.0,
                capsize=2.3,
                zorder=3,
            )
            p_holm = float(test["pvalue_holm"])
            if p_holm < 0.05:
                axis.text(
                    upper + 1.0,
                    y_position,
                    "*",
                    va="center",
                    fontsize=9.0,
                    color=INK,
                )
        axis.axvline(0.0, color=MID_GREY, linewidth=0.8, linestyle="--")
        axis.grid(axis="x", color=GRID_GREY, linewidth=0.55)
        axis.set_axisbelow(True)
        axis.set_title(label)
        axis.set_xlabel(r"$\Delta$ [percentage points]")
    axes[0].set_yticks(
        y_positions,
        [f"vs. {display_method(comparator)}" for comparator in comparators],
    )
    axes[0].invert_yaxis()
    figure.suptitle(
        "Paired endpoint differences: PGRR minus baseline", fontsize=9.3, fontweight="semibold"
    )
    figure.text(
        0.5,
        0.005,
        "Points are paired mean differences; bars are 95% episode-pair bootstrap CIs. "
        "* global Holm-adjusted p<0.05. Positive is favorable only for goal reaching.",
        ha="center",
        fontsize=7.0,
        color=MID_GREY,
    )
    _save_pdf(figure, output)


def safety_efficiency_figure(results: pd.DataFrame, output: Path) -> None:
    """Plot safety against success-conditional time with bootstrap uncertainty."""

    valid = _valid(results)
    required = {"navigation_time_s", "min_human_distance_m"}
    missing = sorted(required - set(valid.columns))
    if missing:
        raise ModerateArtifactError("safety-efficiency figure requires: " + ", ".join(missing))
    methods = method_order(valid["source_policy"].unique())
    figure, axis = plt.subplots(
        figsize=(DOUBLE_COLUMN_WIDTH_IN, 3.0),
        constrained_layout=True,
    )
    offsets = {
        "base": (6, 7),
        "standard": (6, -12),
        "heuristic": (-6, 6),
        "bc_uniform": (-6, -14),
        "pgrr": (6, 8),
    }
    for index, method in enumerate(methods):
        selected = valid.loc[valid["source_policy"] == method]
        successful = selected.loc[selected["outcome"] == "GOAL_REACHED"]
        time = bootstrap_median(
            successful["navigation_time_s"].to_numpy(dtype=float),
            seed=7_100 + index,
        )
        clearance = bootstrap_median(
            selected["min_human_distance_m"].to_numpy(dtype=float),
            seed=8_100 + index,
        )
        if not all(math.isfinite(value) for value in (*time, *clearance)):
            continue
        axis.errorbar(
            time[0],
            clearance[0],
            xerr=np.asarray([[time[0] - time[1]], [time[2] - time[0]]]),
            yerr=np.asarray([[clearance[0] - clearance[1]], [clearance[2] - clearance[0]]]),
            fmt=MARKERS[method],
            color=METHOD_COLORS[method],
            markerfacecolor=METHOD_COLORS[method] if method == "pgrr" else "white",
            markeredgewidth=1.1,
            markersize=7.0,
            elinewidth=1.0,
            capsize=2.5,
            zorder=3,
        )
        x_offset, y_offset = offsets[method]
        axis.annotate(
            f"{display_method(method)}\n{len(successful)}/{len(selected)} goals",
            (time[0], clearance[0]),
            xytext=(x_offset, y_offset),
            textcoords="offset points",
            ha="left" if x_offset > 0 else "right",
            va="bottom" if y_offset > 0 else "top",
            fontsize=7.3,
            color=INK,
        )
    axis.set_title("Safety--efficiency on the complete paired manifest", loc="left")
    axis.set_xlabel("Median navigation time on successful episodes [s]")
    axis.set_ylabel("Median minimum human distance [m]")
    axis.grid(color=GRID_GREY, linewidth=0.55)
    axis.set_axisbelow(True)
    axis.margins(x=0.15, y=0.18)
    axis.text(
        0.01,
        0.01,
        "Error bars: 95% percentile-bootstrap CI\nx: successful episodes; y: all valid episodes",
        transform=axis.transAxes,
        ha="left",
        va="bottom",
        fontsize=7.0,
        color=MID_GREY,
    )
    _save_pdf(figure, output)


def generate_moderate_figures(
    results_path: Path,
    summary_path: Path,
    statistics_path: Path,
    output_dir: Path,
    *,
    expected_condition_count: int,
) -> list[Path]:
    """Validate the three inputs and generate all moderate vector figures."""

    _configure_matplotlib()
    results, _, statistics = load_moderate_artifacts(
        results_path,
        summary_path,
        statistics_path,
        expected_condition_count=expected_condition_count,
    )
    outputs = [
        output_dir / "moderate_outcomes_and_density.pdf",
        output_dir / "moderate_family_success.pdf",
        output_dir / "moderate_paired_effects.pdf",
        output_dir / "moderate_safety_efficiency.pdf",
    ]
    outcome_and_density_figure(results, outputs[0])
    family_success_figure(results, outputs[1])
    paired_effect_figure(statistics, outputs[2])
    safety_efficiency_figure(results, outputs[3])
    return outputs


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--statistics", type=Path, required=True)
    parser.add_argument(
        "--expected-condition-count",
        type=int,
        required=True,
        help=(
            "Exact preregistered test conditions per method; publication generation "
            "fails otherwise."
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "paper/figures")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        outputs = generate_moderate_figures(
            args.results,
            args.summary,
            args.statistics,
            args.output_dir,
            expected_condition_count=args.expected_condition_count,
        )
    except (ModerateArtifactError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
