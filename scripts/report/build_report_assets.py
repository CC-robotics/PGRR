#!/usr/bin/env python3
# ruff: noqa: RUF001
"""Build stage-aware report assets without consulting unapproved results.

The default ``pending`` stage is deliberately data free.  Result-bearing
stages accept only a completed validation snapshot or the locked moderate-v5
test directory.  Historical, pilot, calibration, smoke, and live validation
paths are rejected before a file is opened.
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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
METHODS = ("base", "standard", "heuristic", "bc_uniform", "pgrr")
METHOD_LABELS = {
    "base": "DWB",
    "standard": "Standard",
    "heuristic": "Heuristic",
    "bc_uniform": "Uniform BC",
    "pgrr": "PGRR",
}
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
FORBIDDEN_RESULT_PARTS = (
    "/outputs/final/",
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


def validate_result_path(path: Path, *, stage: str, project_root: Path) -> Path:
    """Resolve a result path and reject every non-authoritative location."""

    resolved = path.expanduser().resolve()
    normalized = resolved.as_posix()
    if any(token in normalized for token in FORBIDDEN_RESULT_PARTS):
        raise ReportInputError(
            "result path is forbidden: historical, pilot, calibration, smoke, "
            "and live validation outputs may not feed reports"
        )
    if resolved.name != "results.parquet":
        raise ReportInputError("the report input must be named results.parquet")

    if stage == "test":
        allowed = (project_root / "outputs/moderate/final").resolve()
    elif stage == "validation":
        allowed = (project_root / "outputs/report_inputs/validation").resolve()
    else:
        raise ReportInputError(f"stage {stage!r} must not receive a result path")
    if not _inside(resolved, allowed):
        raise ReportInputError(
            f"{stage} reports only accept inputs under {allowed.relative_to(project_root)}"
        )
    if not resolved.is_file():
        raise ReportInputError(f"completed report input does not exist: {resolved}")
    return resolved


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
    return results.loc[~results["outcome"].isin(EXCLUDED_OUTCOMES)].copy()


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
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Noto Sans CJK SC", "Liberation Sans", "DejaVu Sans"],
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
            "{} & {} & {:.1f}\% & {:.1f}\% & {:.1f}\% & {:.1f}\% \\\\".format(
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
            "",
        )
    )


def build_report_assets(
    *,
    stage: str,
    results_path: Path | None,
    output_dir: Path,
    project_root: Path = PROJECT_ROOT,
    expected_conditions: int | None = None,
) -> dict[str, Any]:
    """Build deterministic report inputs and return their machine-readable data."""

    if stage not in {"pending", "validation", "test"}:
        raise ReportInputError("stage must be one of: pending, validation, test")
    output_dir.mkdir(parents=True, exist_ok=True)
    if stage == "pending":
        if results_path is not None:
            raise ReportInputError("pending stage must not receive or inspect a results file")
        data: dict[str, Any] = {
            "schema_version": 1,
            "stage": "pending",
            "results_available": False,
            "notice": "Validation is running; no numerical result is approved for reporting.",
            "author_alias": "Charles Chen",
        }
        (output_dir / "report_stage.tex").write_text(_pending_macros(), encoding="utf-8")
        (output_dir / "result_table.tex").write_text(
            "% Results are intentionally unavailable in pending mode.\n", encoding="utf-8"
        )
        (output_dir / "report_data.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return data

    if results_path is None:
        raise ReportInputError(f"stage {stage!r} requires an explicit completed results path")
    approved = validate_result_path(results_path, stage=stage, project_root=project_root)
    conditions = expected_conditions or (120 if stage == "test" else 72)
    results = pd.read_parquet(approved)
    validate_results(results, stage=stage, expected_conditions=conditions)
    valid = _valid_rows(results)
    summary = _method_summary(results)
    data = {
        "schema_version": 1,
        "stage": stage,
        "results_available": True,
        "results_path": approved.relative_to(project_root).as_posix(),
        "results_sha256": _sha256(approved),
        "condition_count": conditions,
        "episode_count": len(results),
        "valid_episode_count": len(valid),
        "excluded_episode_count": int(len(results) - len(valid)),
        "method_summary": summary,
        "density_summary": _density_summary(results),
        "family_summary": _family_summary(results),
        "paired_effects": _paired_effects(results),
        "author_alias": "Charles Chen",
    }
    _configure_plotting()
    _outcome_figure(results, output_dir)
    _density_figure(results, output_dir)
    _family_figure(results, output_dir)
    _safety_efficiency_figure(results, output_dir)
    (output_dir / "result_table.tex").write_text(_result_table(summary), encoding="utf-8")
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
