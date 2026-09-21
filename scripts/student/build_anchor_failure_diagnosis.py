#!/usr/bin/env python3
"""Build a reproducible two-anchor recovery failure diagnosis."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ANCHORS = (
    "goal_approach_lateral_interruption",
    "lead_pedestrian_sudden_stop",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_diagnosis(
    pair_rows: list[dict[str, str]],
    progress: dict[str, Any],
    attribution: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    pairs = {row["family"]: row for row in pair_rows}
    episodes = {row["family"]: row for row in progress["episodes"]}
    output = []
    for family in ANCHORS:
        pair = pairs[family]
        episode = episodes[family]
        learned = [
            row for row in attribution["learned_events"] if row["family"] == family
        ]
        cycles = [row for row in contract["cycles"] if row["family"] == family]
        action_counts = Counter(row["action_name"] for row in learned)
        output.append(
            {
                "family": family,
                "base_outcome": pair["base_outcome"],
                "pgrr_outcome": pair["pgrr_outcome"],
                "initial_goal_distance_m": episode["initial_original_goal_distance_m"],
                "final_goal_distance_m": episode["final_original_goal_distance_m"],
                "net_goal_progress_m": episode["net_original_goal_progress_m"],
                "recovery_cycle_count": episode["recovery_cycle_count"],
                "completed_rejoin_count": episode["completed_rejoin_count"],
                "positive_progress_cycle_count": episode[
                    "positive_progress_cycle_count"
                ],
                "nonpositive_progress_cycle_count": episode[
                    "nonpositive_progress_cycle_count"
                ],
                "hazard_cleared_cycle_count": sum(
                    bool(row["hazard_cleared"]) for row in cycles
                ),
                "meaningful_progress_cycle_count": sum(
                    bool(row["meaningful_task_progress"]) for row in cycles
                ),
                "rapid_retrigger_count": sum(
                    bool(row["rapid_retrigger"]) for row in cycles
                ),
                "learned_decision_count": len(learned),
                "learned_action_counts": dict(sorted(action_counts.items())),
                "only_wait_backup_allowed_count": sum(
                    bool(row["only_wait_backup_allowed"]) for row in learned
                ),
                "alternative_action_available_count": sum(
                    bool(row["alternative_action_available"]) for row in learned
                ),
                "mask_parseable_count": sum(bool(row["mask_parseable"]) for row in learned),
            }
        )

    total_decisions = sum(row["learned_decision_count"] for row in output)
    wait_backup_only = sum(row["only_wait_backup_allowed_count"] for row in output)
    total_cycles = sum(row["recovery_cycle_count"] for row in output)
    meaningful_cycles = sum(row["meaningful_progress_cycle_count"] for row in output)
    return {
        "schema_version": 1,
        "scope": "two_train_only_anchor_runs_descriptive_not_causal",
        "anchors": output,
        "aggregate": {
            "anchor_count": len(output),
            "pgrr_goal_reached_count": sum(
                row["pgrr_outcome"] == "GOAL_REACHED" for row in output
            ),
            "recovery_cycle_count": total_cycles,
            "hazard_cleared_cycle_count": sum(
                row["hazard_cleared_cycle_count"] for row in output
            ),
            "meaningful_progress_cycle_count": meaningful_cycles,
            "completed_rejoin_count": sum(
                row["completed_rejoin_count"] for row in output
            ),
            "learned_decision_count": total_decisions,
            "only_wait_backup_allowed_count": wait_backup_only,
            "only_wait_backup_allowed_fraction": (
                round(wait_backup_only / total_decisions, 6) if total_decisions else None
            ),
            "alternative_action_available_count": sum(
                row["alternative_action_available_count"] for row in output
            ),
        },
        "findings": [
            {
                "rank": 1,
                "name": "candidate_availability_bottleneck",
                "evidence": (
                    f"{wait_backup_only}/{total_decisions} learned decisions exposed only "
                    "WAIT and BACKUP in the logged final mask"
                ),
                "boundary": (
                    "final-mask correlation; exact upstream removal attribution requires "
                    "a fresh full-layer trace"
                ),
            },
            {
                "rank": 2,
                "name": "hazard_clear_without_task_progress",
                "evidence": (
                    f"hazard cleared in {sum(row['hazard_cleared_cycle_count'] for row in output)}"
                    f"/{total_cycles} cycles, but meaningful progress occurred in "
                    f"{meaningful_cycles}/{total_cycles}"
                ),
                "boundary": "the progress contract is a train-only diagnostic probe",
            },
            {
                "rank": 3,
                "name": "rejoin_is_not_sufficient",
                "evidence": (
                    f"{sum(row['completed_rejoin_count'] for row in output)} completed "
                    "rejoins still produced zero positive-progress recovery cycles"
                ),
                "boundary": "observational evidence does not prove rejoin logic is causal",
            },
        ],
        "next_gate": {
            "action": (
                "capture an exact full-layer mask trace on both anchors before changing "
                "candidate filtering or policy logic"
            ),
            "reason": (
                "the current evidence localizes the bottleneck to final candidate "
                "availability, but cannot yet identify the responsible upstream layer"
            ),
            "algorithm_change_authorized": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    aggregate = report["aggregate"]
    lines = [
        "# Two-anchor recovery failure diagnosis",
        "",
        "> Two train-only runs. Descriptive evidence only; no causal or superiority claim.",
        "",
        (
            "| Anchor | Base | PGRR | Final goal distance | Cycles | Positive "
            "cycles | Rejoins | WAIT/BACKUP-only masks |"
        ),
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in report["anchors"]:
        lines.append(
            f"| `{row['family']}` | {row['base_outcome']} | {row['pgrr_outcome']} | "
            f"{row['final_goal_distance_m']:.2f} m | {row['recovery_cycle_count']} | "
            f"{row['positive_progress_cycle_count']} | {row['completed_rejoin_count']} | "
            f"{row['only_wait_backup_allowed_count']}/{row['learned_decision_count']} |"
        )
    lines.extend(
        [
            "",
            "## Main result",
            "",
            f"Across both anchors, {aggregate['hazard_cleared_cycle_count']}/"
            f"{aggregate['recovery_cycle_count']} recovery cycles cleared the diagnosed "
            f"hazard, but {aggregate['meaningful_progress_cycle_count']}/"
            f"{aggregate['recovery_cycle_count']} made meaningful task progress. "
            f"The logged final mask allowed only WAIT/BACKUP for "
            f"{aggregate['only_wait_backup_allowed_count']}/"
            f"{aggregate['learned_decision_count']} learned decisions.",
            "",
            "This points first to a candidate-availability bottleneck, not simply a bad "
            "choice among many safe subgoals. It is not yet causal attribution because "
            "these historical runs did not record every upstream mask layer exactly.",
            "",
            "## Next gate",
            "",
            "Run one non-frozen, full-layer mask-trace episode for each anchor. Only after "
            "the exact removal layer is identified should candidate filtering or policy "
            "logic change. Do not tune on the frozen test set.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--attribution", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    with args.pairs.open(encoding="utf-8", newline="") as stream:
        pair_rows = list(csv.DictReader(stream))
    report = build_diagnosis(
        pair_rows,
        _read_json(args.progress),
        _read_json(args.attribution),
        _read_json(args.contract),
    )
    report["sources"] = {
        name: {"path": str(path), "sha256": _sha256(path)}
        for name, path in {
            "pairs": args.pairs,
            "progress": args.progress,
            "attribution": args.attribution,
            "contract": args.contract,
        }.items()
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report["aggregate"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
