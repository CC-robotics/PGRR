"""Render the complete eight-family development pilot as CSV and Markdown."""

from __future__ import annotations

import argparse
import csv
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "outputs/student/eight_family_pilot/minimal_pair_progress.json"
DEFAULT_OUTPUT = ROOT / "outputs/student/eight_family_pilot"
FIELDS = [
    "family_index",
    "family",
    "base_outcome",
    "base_collision_type",
    "base_goal_distance_m",
    "pgrr_outcome",
    "pgrr_goal_distance_m",
    "pgrr_recovery_triggered",
    "pgrr_decision_events",
    "pgrr_temporary_subgoals",
    "pgrr_original_goal_restores",
]


def _collision_type(run: dict[str, Any]) -> str:
    if run["outcome"] != "COLLISION":
        return "none"
    detail = run["outcome_detail"]
    if detail == "privileged robot-human overlap":
        return "dynamic_actor"
    if "static scenario geometry" in detail:
        return "static_geometry"
    return "unattributed"


def summarize(report: dict[str, Any]) -> dict[str, Any]:
    pairs = report["pairs"]
    if report["complete_pair_count"] != 8 or len(pairs) != 8:
        raise ValueError("summary requires all eight complete Base/PGRR pairs")
    rows = []
    infrastructure_attempts = 0
    for pair in sorted(pairs, key=lambda item: item["family_index"]):
        base, pgrr = pair["runs"]["base"], pair["runs"]["pgrr"]
        trace = pgrr["recovery_trace"]
        for run in (base, pgrr):
            infrastructure_attempts += sum(
                bool(attempt["infrastructure_attempt"])
                for attempt in run["attempt_history"]
            )
        rows.append(
            {
                "family_index": pair["family_index"],
                "family": pair["family"],
                "base_outcome": base["outcome"],
                "base_collision_type": _collision_type(base),
                "base_goal_distance_m": round(base["physical_goal_distance_m"], 3),
                "pgrr_outcome": pgrr["outcome"],
                "pgrr_goal_distance_m": round(pgrr["physical_goal_distance_m"], 3),
                "pgrr_recovery_triggered": pair["paired_interpretation"][
                    "pgrr_recovery_triggered"
                ],
                "pgrr_decision_events": trace["decision_event_count"],
                "pgrr_temporary_subgoals": trace["temporary_subgoal_decision_count"],
                "pgrr_original_goal_restores": trace["original_goal_restored_event_count"],
            }
        )
    base_counts = Counter(row["base_outcome"] for row in rows)
    pgrr_counts = Counter(row["pgrr_outcome"] for row in rows)
    collision_types = Counter(row["base_collision_type"] for row in rows)
    aggregate = {
        "complete_pair_count": len(rows),
        "valid_algorithm_episode_count": 2 * len(rows),
        "preserved_infrastructure_attempt_count": infrastructure_attempts,
        "base_outcome_counts": dict(sorted(base_counts.items())),
        "pgrr_outcome_counts": dict(sorted(pgrr_counts.items())),
        "base_dynamic_actor_collisions": collision_types["dynamic_actor"],
        "base_static_geometry_collisions": collision_types["static_geometry"],
        "pgrr_recovery_triggered_pairs": sum(row["pgrr_recovery_triggered"] for row in rows),
        "pgrr_total_decision_events": sum(row["pgrr_decision_events"] for row in rows),
        "pgrr_total_temporary_subgoals": sum(row["pgrr_temporary_subgoals"] for row in rows),
        "pgrr_total_original_goal_restores": sum(
            row["pgrr_original_goal_restores"] for row in rows
        ),
        "goal_reached_count_both_methods": base_counts["GOAL_REACHED"]
        + pgrr_counts["GOAL_REACHED"],
    }
    return {"aggregate": aggregate, "rows": rows}


def _render_csv(rows: list[dict[str, Any]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _render_markdown(summary: dict[str, Any]) -> str:
    aggregate, rows = summary["aggregate"], summary["rows"]
    lines = [
        "# Eight-family minimal Base/PGRR development pilot",
        "",
        (
            "> Development evidence only. Train scenarios; no held-out test, tuning, "
            "or superiority claim."
        ),
        "",
        (
            "| # | Family | Base | Collision type | PGRR | Base dist. | PGRR dist. | "
            "Triggered | Decisions | Subgoals | Restores |"
        ),
        "|---:|---|---|---|---|---:|---:|---|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['family_index'] + 1} | {row['family']} | {row['base_outcome']} | "
            f"{row['base_collision_type']} | {row['pgrr_outcome']} | "
            f"{row['base_goal_distance_m']:.3f} | {row['pgrr_goal_distance_m']:.3f} | "
            f"{str(row['pgrr_recovery_triggered']).lower()} | "
            f"{row['pgrr_decision_events']} | {row['pgrr_temporary_subgoals']} | "
            f"{row['pgrr_original_goal_restores']} |"
        )
    lines.extend(
        [
            "",
            "## Aggregate diagnostic",
            "",
            f"- Complete pairs: {aggregate['complete_pair_count']}/8.",
            f"- Base outcomes: {aggregate['base_outcome_counts']}.",
            f"- PGRR outcomes: {aggregate['pgrr_outcome_counts']}.",
            f"- Base collisions: {aggregate['base_dynamic_actor_collisions']} dynamic actor, "
            f"{aggregate['base_static_geometry_collisions']} static geometry.",
            f"- PGRR recovery triggered in {aggregate['pgrr_recovery_triggered_pairs']}/8 pairs.",
            f"- PGRR decisions: {aggregate['pgrr_total_decision_events']}; temporary subgoals: "
            f"{aggregate['pgrr_total_temporary_subgoals']}; original-goal restores: "
            f"{aggregate['pgrr_total_original_goal_restores']}.",
            f"- Goal reaches across both methods: {aggregate['goal_reached_count_both_methods']}.",
            (
                "- Preserved infrastructure attempts: "
                f"{aggregate['preserved_infrastructure_attempt_count']}."
            ),
            "",
            "The pilot exposes a safety/completion tradeoff: PGRR had no collision in the "
            "six pairs "
            "where Base collided, but it did not reach the goal in any pair. The comparator phase "
            "must remain paused because the minimal-pair health criterion was not met.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = json.loads(args.input.read_text(encoding="utf-8"))
    summary = summarize(report)
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "minimal_pair_summary.csv").write_bytes(
        _render_csv(summary["rows"]).encode("utf-8")
    )
    (args.output_root / "minimal_pair_summary.md").write_bytes(
        _render_markdown(summary).encode("utf-8")
    )
    print(json.dumps(summary["aggregate"], indent=2))


if __name__ == "__main__":
    main()
