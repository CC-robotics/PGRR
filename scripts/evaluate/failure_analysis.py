#!/usr/bin/env python3
"""Generate an evidence-bounded failure report from the locked final results.

The report is deliberately derived from ``outputs/final/results.parquet``.  It
does not search pilot outputs and does not inspect raw telemetry to invent
additional labels.  Raw JSONL files are opened only to verify the SHA-256 shown
for representative episodes.
"""

from __future__ import annotations

import argparse
import hashlib
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS = ROOT / "outputs/final/results.parquet"
DEFAULT_OUTPUT = ROOT / "outputs/final/failure_analysis.md"
DEFAULT_RAW_DIR = ROOT / "data/raw"

KNOWN_OUTCOMES = frozenset(
    {
        "GOAL_REACHED",
        "COLLISION",
        "TIMEOUT",
        "PLANNER_FAILURE",
        "SIMULATOR_FAILURE",
        "INVALID_RESET",
    }
)
EXCLUDED_OUTCOMES = frozenset({"SIMULATOR_FAILURE", "INVALID_RESET"})
REQUIRED_COLUMNS = frozenset(
    {
        "episode_id",
        "source_policy",
        "family",
        "density",
        "outcome",
        "outcome_detail",
        "included_in_algorithm_metrics",
        "project_commit",
        "raw_sha256",
        "timeline_time_s",
        "timeline_distance_to_goal_m",
        "timeline_recovery_state",
        "recovery_trigger_count",
        "recovery_action_sample_count",
        "intervention_ratio",
    }
)

CATEGORY_ORDER = (
    "collision_human",
    "collision_static",
    "collision_unattributed",
    "timeout_stagnation",
    "timeout_other",
    "timeout_unresolved",
    "planner_abort",
    "excluded_simulator_failure",
    "excluded_invalid_reset",
)
CATEGORY_LABELS = {
    "collision_human": "Human collision",
    "collision_static": "Static-geometry collision",
    "collision_unattributed": "Collision, contact type unresolved",
    "timeout_stagnation": "Timeout / terminal stagnation",
    "timeout_other": "Timeout with terminal progress",
    "timeout_unresolved": "Timeout, terminal progress unavailable",
    "planner_abort": "Planner abort",
    "excluded_simulator_failure": "Simulator failure (excluded)",
    "excluded_invalid_reset": "Invalid reset (excluded)",
}

HUMAN_DETAIL_TOKENS = (
    "robot-human",
    "robot human",
    "human overlap",
    "pedestrian",
    "person contact",
)
STATIC_DETAIL_TOKENS = (
    "static scenario geometry",
    "static geometry",
    "static obstacle",
    "wall contact",
    "map geometry",
)


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of a file without loading it all into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sequence(value: object) -> np.ndarray | None:
    if isinstance(value, np.ndarray):
        array = value
    elif isinstance(value, (list, tuple, pd.Series)):
        array = np.asarray(value)
    else:
        return None
    try:
        numeric = array.astype(np.float64)
    except (TypeError, ValueError):
        return None
    return numeric if numeric.ndim == 1 else None


def terminal_progress(
    row: Mapping[str, Any],
    *,
    window_s: float,
) -> tuple[float, float] | None:
    """Return net goal-distance progress and the measured terminal horizon.

    The start value is linearly interpolated at exactly ``window_s`` before the
    final timestamp.  A full window is required so a short or malformed trace
    is reported as unavailable instead of being silently extrapolated.
    """

    times = _sequence(row.get("timeline_time_s"))
    distances = _sequence(row.get("timeline_distance_to_goal_m"))
    if (
        times is None
        or distances is None
        or len(times) != len(distances)
        or len(times) < 2
        or not np.all(np.isfinite(times))
        or not np.all(np.isfinite(distances))
        or np.any(np.diff(times) <= 0.0)
    ):
        return None
    horizon = float(times[-1] - times[0])
    if horizon + 1.0e-9 < window_s:
        return None
    start_time = float(times[-1] - window_s)
    start_distance = float(np.interp(start_time, times, distances))
    progress = start_distance - float(distances[-1])
    return progress, window_s


def classify_episode(
    row: Mapping[str, Any],
    *,
    terminal_window_s: float,
    stagnation_threshold_m: float,
) -> tuple[str | None, str, float | None]:
    """Classify a terminal result using only columns in the final table."""

    outcome = str(row.get("outcome", ""))
    detail = str(row.get("outcome_detail", "") or "").strip()
    normalized_detail = detail.casefold()
    if outcome == "GOAL_REACHED":
        return None, "terminal outcome is GOAL_REACHED", None
    if outcome == "COLLISION":
        if any(token in normalized_detail for token in HUMAN_DETAIL_TOKENS):
            return "collision_human", f"explicit outcome detail: {detail}", None
        if any(token in normalized_detail for token in STATIC_DETAIL_TOKENS):
            return "collision_static", f"explicit outcome detail: {detail}", None
        return (
            "collision_unattributed",
            f"collision detail does not identify the contact type: {detail or 'empty detail'}",
            None,
        )
    if outcome == "TIMEOUT":
        measured = terminal_progress(row, window_s=terminal_window_s)
        if measured is None:
            return (
                "timeout_unresolved",
                f"timeout; no valid {terminal_window_s:.1f} s terminal distance window",
                None,
            )
        progress, _ = measured
        if progress < stagnation_threshold_m:
            return (
                "timeout_stagnation",
                f"timeout; terminal {terminal_window_s:.1f} s net goal progress "
                f"{progress:.3f} m < {stagnation_threshold_m:.3f} m",
                progress,
            )
        return (
            "timeout_other",
            f"timeout; terminal {terminal_window_s:.1f} s net goal progress "
            f"{progress:.3f} m >= {stagnation_threshold_m:.3f} m",
            progress,
        )
    if outcome == "PLANNER_FAILURE":
        return "planner_abort", f"terminal PLANNER_FAILURE: {detail or 'empty detail'}", None
    if outcome == "SIMULATOR_FAILURE":
        return (
            "excluded_simulator_failure",
            f"excluded simulator outcome: {detail or 'empty detail'}",
            None,
        )
    if outcome == "INVALID_RESET":
        return (
            "excluded_invalid_reset",
            f"excluded reset outcome: {detail or 'empty detail'}",
            None,
        )
    raise ValueError(f"unknown terminal outcome: {outcome!r}")


def _validate_results(results: pd.DataFrame) -> str:
    missing = sorted(REQUIRED_COLUMNS - set(results.columns))
    if missing:
        raise ValueError(f"final results are missing required columns: {missing}")
    if results.empty:
        raise ValueError("final results are empty")
    if results["episode_id"].isna().any() or results["episode_id"].astype(str).duplicated().any():
        raise ValueError("final episode_id values must be non-null and unique")
    outcomes = set(results["outcome"].astype(str))
    if unexpected := sorted(outcomes - KNOWN_OUTCOMES):
        raise ValueError(f"final results contain unknown outcomes: {unexpected}")
    if results["included_in_algorithm_metrics"].isna().any():
        raise ValueError("included_in_algorithm_metrics contains missing values")
    for row in results.itertuples(index=False):
        included = bool(row.included_in_algorithm_metrics)
        expected = str(row.outcome) not in EXCLUDED_OUTCOMES
        if included != expected:
            raise ValueError(
                f"included_in_algorithm_metrics disagrees with outcome for {row.episode_id}"
            )
    commits = sorted(str(value) for value in results["project_commit"].dropna().unique())
    if len(commits) != 1 or not commits[0]:
        raise ValueError(f"final results must use exactly one project commit: {commits}")
    return commits[0]


def classify_results(
    results: pd.DataFrame,
    *,
    terminal_window_s: float,
    stagnation_threshold_m: float,
) -> pd.DataFrame:
    """Return a classified copy; never mutate the loaded final table."""

    _validate_results(results)
    classified = results.copy(deep=True)
    categories: list[str | None] = []
    evidence: list[str] = []
    progress: list[float | None] = []
    for row in classified.to_dict(orient="records"):
        category, reason, terminal_progress_m = classify_episode(
            row,
            terminal_window_s=terminal_window_s,
            stagnation_threshold_m=stagnation_threshold_m,
        )
        categories.append(category)
        evidence.append(reason)
        progress.append(terminal_progress_m)
    classified["failure_category"] = categories
    classified["classification_evidence"] = evidence
    classified["terminal_window_progress_m"] = progress
    return classified


def _markdown(value: object) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).replace("\n", " ").replace("\r", " ").replace("|", "\\|")


def _density_rank(value: object) -> int:
    return {"low": 0, "medium": 1, "high": 2}.get(str(value), 3)


def _representatives(group: pd.DataFrame, limit: int = 3) -> pd.DataFrame:
    """Select deterministic, diverse examples without outcome-dependent cherry-picking."""

    ordered = group.copy()
    ordered["_density_rank"] = ordered["density"].map(_density_rank)
    ordered = ordered.sort_values(
        ["source_policy", "family", "_density_rank", "episode_id"], kind="stable"
    )
    selected: list[int] = []
    used_methods: set[str] = set()
    used_families: set[str] = set()
    # First cover methods, then scenario families, then fill lexicographically.
    for prefer in ("source_policy", "family", None):
        for index, row in ordered.iterrows():
            if index in selected:
                continue
            method = str(row["source_policy"])
            family = str(row["family"])
            if prefer == "source_policy" and method in used_methods:
                continue
            if prefer == "family" and family in used_families:
                continue
            selected.append(index)
            used_methods.add(method)
            used_families.add(family)
            if len(selected) == limit:
                return ordered.loc[selected].drop(columns="_density_rank")
    return ordered.loc[selected].drop(columns="_density_rank")


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _verified_raw_reference(row: Mapping[str, Any], raw_dir: Path, root: Path) -> tuple[str, str]:
    episode_id = str(row["episode_id"])
    path = raw_dir / f"{episode_id}.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"representative raw telemetry is missing: {path}")
    declared = str(row["raw_sha256"])
    if len(declared) != 64:
        raise ValueError(f"invalid raw_sha256 for {episode_id}: {declared!r}")
    actual = sha256_file(path)
    if actual != declared:
        raise ValueError(
            f"raw telemetry SHA-256 mismatch for {episode_id}: declared={declared}, actual={actual}"
        )
    return _relative_path(path, root), actual


def _state_timeline_has_recovery(value: object) -> bool:
    if not isinstance(value, (np.ndarray, list, tuple)):
        return False
    active = {"PENDING_RECOVERY", "RECOVERY", "REJOIN", "EMERGENCY_STOP"}
    return any(str(state) in active for state in value)


def _action_count(group: pd.DataFrame, *, action: str) -> int | None:
    direct_column = f"{action.lower()}_action_sample_count"
    if direct_column in group.columns:
        values = pd.to_numeric(group[direct_column], errors="coerce")
        return int(values.fillna(0).sum())
    if "timeline_recovery_action" not in group.columns:
        return None
    action_id = {"WAIT": 21, "BACKUP": 22}[action]
    count = 0
    for timeline in group["timeline_recovery_action"]:
        if not isinstance(timeline, (np.ndarray, list, tuple)):
            continue
        count += sum(int(value) == action_id for value in timeline)
    return count


def build_report(
    results: pd.DataFrame,
    *,
    results_path: Path,
    raw_dir: Path,
    root: Path,
    terminal_window_s: float = 4.0,
    stagnation_threshold_m: float = 0.15,
) -> str:
    """Build the Markdown report and verify every cited raw artifact."""

    if terminal_window_s <= 0.0:
        raise ValueError("terminal_window_s must be positive")
    if stagnation_threshold_m < 0.0:
        raise ValueError("stagnation_threshold_m must be non-negative")
    project_commit = _validate_results(results)
    classified = classify_results(
        results,
        terminal_window_s=terminal_window_s,
        stagnation_threshold_m=stagnation_threshold_m,
    )
    failure_rows = classified[classified["failure_category"].notna()].copy()
    valid = classified[classified["included_in_algorithm_metrics"].astype(bool)].copy()
    results_sha = sha256_file(results_path)
    source_path = _relative_path(results_path, root)

    excluded_attempts = (
        int(pd.to_numeric(classified["excluded_attempt_count"], errors="coerce").fillna(0).sum())
        if "excluded_attempt_count" in classified.columns
        else 0
    )
    lines = [
        "# Final Failure Analysis",
        "",
        "This report is generated from the locked final result table only. "
        "It describes terminal outcomes and recorded telemetry; it does not infer causal "
        "mechanisms that are absent from those artifacts.",
        "",
        "## Provenance and scope",
        "",
        f"- Source: `{source_path}`",
        f"- Source SHA-256: `{results_sha}`",
        f"- Project commit recorded by all rows: `{project_commit}`",
        f"- Manifest result rows: {len(classified)}",
        f"- Algorithm episodes: {len(valid)}",
        f"- Excluded terminal rows: {len(classified) - len(valid)}",
        f"- Excluded physical attempts retained by the runner: {excluded_attempts}",
        "",
        "## Classification policy",
        "",
        "- `collision_human` and `collision_static` require an explicit contact type in "
        "  `outcome_detail`. A generic LiDAR or collision message remains "
        "  `collision_unattributed`.",
        f"- `timeout_stagnation` means less than {stagnation_threshold_m:.3f} m net "
        f"  goal-distance progress in the final {terminal_window_s:.1f} s, computed from the "
        "  stored timeline. It is a kinematic observation, not a diagnosis of why progress "
        "  stopped.",
        "- `planner_abort` is assigned only to the terminal `PLANNER_FAILURE` outcome.",
        "- Simulator failures and invalid resets are shown separately and remain excluded "
        "  from algorithm metrics.",
        "",
        "## Category totals",
        "",
        "| Category | Count | Metric scope |",
        "|---|---:|---|",
    ]
    for category in CATEGORY_ORDER:
        group = failure_rows[failure_rows["failure_category"] == category]
        scope = "excluded technical outcome" if category.startswith("excluded_") else "algorithm"
        lines.append(f"| {CATEGORY_LABELS[category]} | {len(group)} | {scope} |")

    lines.extend(
        [
            "",
            "## Counts by method, scenario family, and density",
            "",
            "Only observed non-success categories are listed; zero-count categories remain "
            "visible in the totals above.",
            "",
            "| Category | Method | Family | Density | Episodes |",
            "|---|---|---|---|---:|",
        ]
    )
    if failure_rows.empty:
        lines.append("| — | — | — | — | 0 |")
    else:
        grouped = (
            failure_rows.groupby(
                ["failure_category", "source_policy", "family", "density"],
                dropna=False,
                sort=True,
            )
            .size()
            .reset_index(name="episodes")
        )
        grouped["_category"] = grouped["failure_category"].map(
            {category: index for index, category in enumerate(CATEGORY_ORDER)}
        )
        grouped["_density"] = grouped["density"].map(_density_rank)
        grouped = grouped.sort_values(
            ["_category", "source_policy", "family", "_density"], kind="stable"
        )
        for row in grouped.to_dict(orient="records"):
            lines.append(
                "| "
                + " | ".join(
                    (
                        _markdown(CATEGORY_LABELS[str(row["failure_category"])]),
                        _markdown(row["source_policy"]),
                        _markdown(row["family"]),
                        _markdown(row["density"]),
                        str(int(row["episodes"])),
                    )
                )
                + " |"
            )

    lines.extend(
        [
            "",
            "## Recorded recovery behavior",
            "",
            "The trigger and intervention columns below are descriptive aggregates from the "
            "final table. They are not used to attribute an outcome to the recovery policy.",
            "",
            "| Method | Episodes | Non-success outcomes | Trigger count | Trigger mean | "
            "Recovery-timeline episodes | Intervention ratio mean | Non-CONTINUE samples | "
            "WAIT samples | BACKUP samples |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    wait_available = False
    backup_available = False
    for method, group in valid.groupby("source_policy", sort=True):
        trigger_values = pd.to_numeric(group["recovery_trigger_count"], errors="coerce")
        intervention_values = pd.to_numeric(group["intervention_ratio"], errors="coerce")
        action_values = pd.to_numeric(group["recovery_action_sample_count"], errors="coerce")
        wait_count = _action_count(group, action="WAIT")
        backup_count = _action_count(group, action="BACKUP")
        wait_available |= wait_count is not None
        backup_available |= backup_count is not None
        non_success = int((group["outcome"] != "GOAL_REACHED").sum())
        recovery_timelines = int(
            group["timeline_recovery_state"].map(_state_timeline_has_recovery).sum()
        )
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown(method),
                    str(len(group)),
                    str(non_success),
                    str(int(trigger_values.fillna(0).sum())),
                    f"{trigger_values.mean():.3f}" if trigger_values.notna().any() else "N/A",
                    str(recovery_timelines),
                    (
                        f"{intervention_values.mean():.3f}"
                        if intervention_values.notna().any()
                        else "N/A"
                    ),
                    str(int(action_values.fillna(0).sum())),
                    str(wait_count) if wait_count is not None else "not recorded",
                    str(backup_count) if backup_count is not None else "not recorded",
                )
            )
            + " |"
        )
    if not wait_available or not backup_available:
        missing_actions = [
            name
            for name, available in (("WAIT", wait_available), ("BACKUP", backup_available))
            if not available
        ]
        lines.extend(
            [
                "",
                f"Action-specific counts for {', '.join(missing_actions)} are not present in "
                "`results.parquet`; this report does not infer them from recovery state, "
                "terminal outcome, or free-text detail.",
            ]
        )

    lines.extend(
        [
            "",
            "## Deterministic representative episodes",
            "",
            "For each category, at most three rows are selected by a fixed method/family/"
            "density/episode ordering with method and family coverage preferred. The listed "
            "raw files are SHA-256 verified against the final result table.",
        ]
    )
    for category in CATEGORY_ORDER:
        group = failure_rows[failure_rows["failure_category"] == category]
        lines.extend(["", f"### {CATEGORY_LABELS[category]}", ""])
        if group.empty:
            lines.append("No final episode was assigned to this category.")
            continue
        lines.extend(
            [
                "| Episode | Method | Family | Density | Evidence | Raw path | Raw SHA-256 |",
                "|---|---|---|---|---|---|---|",
            ]
        )
        for row in _representatives(group).to_dict(orient="records"):
            raw_path, raw_sha = _verified_raw_reference(row, raw_dir, root)
            lines.append(
                "| "
                + " | ".join(
                    (
                        f"`{_markdown(row['episode_id'])}`",
                        _markdown(row["source_policy"]),
                        _markdown(row["family"]),
                        _markdown(row["density"]),
                        _markdown(row["classification_evidence"]),
                        f"`{_markdown(raw_path)}`",
                        f"`{raw_sha}`",
                    )
                )
                + " |"
            )

    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "This artifact supports counts, terminal contact labels explicitly supplied by "
            "the evaluator, terminal goal-progress observations, and recorded recovery "
            "activity. It does not by itself establish that a trigger, WAIT/BACKUP choice, "
            "planner decision, or pedestrian behavior caused a terminal outcome.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--terminal-window-s", type=float, default=4.0)
    parser.add_argument("--stagnation-threshold-m", type=float, default=0.15)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    results_path = args.results.resolve()
    output_path = args.output.resolve()
    raw_dir = args.raw_dir.resolve()
    if not results_path.is_file():
        raise FileNotFoundError(
            f"locked final results are required; no pilot fallback is allowed: {results_path}"
        )
    if output_path == results_path:
        raise ValueError("failure report output must not overwrite results.parquet")
    results = pd.read_parquet(results_path)
    report = build_report(
        results,
        results_path=results_path,
        raw_dir=raw_dir,
        root=ROOT,
        terminal_window_s=args.terminal_window_s,
        stagnation_threshold_m=args.stagnation_threshold_m,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(report, encoding="utf-8")
    temporary.replace(output_path)
    print(f"Final failure analysis PASS: rows={len(results)} output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
