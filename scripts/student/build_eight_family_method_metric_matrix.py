#!/usr/bin/env python3
"""Build a paper-facing algorithm/scenario/metric matrix from checked-in evidence."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import yaml

MECHANISM_BY_TARGET = {
    "collision_risk": {
        "components": ["failure trigger", "safe action mask", "WAIT/BACKUP/subgoal"],
        "question": "Does recovery activate before contact and preserve a safe route back?",
        "diagnostics": ["triggered", "time_to_first_recovery_s", "minimum_clearance_m"],
    },
    "oscillation": {
        "components": ["failure trigger", "direction commitment", "recovery memory"],
        "question": "Does the recovery avoid repeated reversals and produce task progress?",
        "diagnostics": ["recovery_cycle_count", "action_switch_count", "cycle_progress_m"],
    },
    "freeze": {
        "components": ["failure trigger", "WAIT/BACKUP/subgoal/REPLAN", "rejoin"],
        "question": "Does a bounded recovery regain progress and restore the original goal?",
        "diagnostics": ["stationary_duration_s", "cycle_progress_m", "goal_restore_count"],
    },
    "deadlock": {
        "components": ["failure trigger", "lateral subgoal/WAIT/BACKUP", "rejoin"],
        "question": "Does the robot break reciprocal blocking without collision?",
        "diagnostics": ["deadlock_duration_s", "temporary_subgoal_count", "cycle_progress_m"],
    },
    "planner_failure": {
        "components": ["planner-failure trigger", "REPLAN/temporary subgoal", "goal restore"],
        "question": "Can planning be recovered while preserving the original task goal?",
        "diagnostics": ["planner_failure_count", "replan_count", "goal_restore_count"],
    },
    "timeout": {
        "components": ["failure trigger", "bounded recovery", "rejoin"],
        "question": "Where does progress stop despite collision avoidance?",
        "diagnostics": ["cycle_progress_m", "rapid_retrigger_count", "final_goal_distance_m"],
    },
}

PRIMARY_METRICS = ["GOAL_REACHED", "COLLISION", "TIMEOUT"]
COST_METRICS = ["completion_time_s", "path_length_m", "angular_jerk"]


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected YAML object: {path}")
    return value


def _target_parts(value: str) -> list[str]:
    normalized = value.replace("freeze_or_deadlock", "freeze_or_deadlock")
    return normalized.split("_or_")


def build_matrix(draft_path: Path, pilot_path: Path, pair_csv: Path) -> dict[str, Any]:
    draft = _load_yaml(draft_path)
    pilot = _load_yaml(pilot_path)
    with pair_csv.open(encoding="utf-8", newline="") as stream:
        pairs = {row["family"]: row for row in csv.DictReader(stream)}
    pilot_families = {item["id"]: item for item in pilot["families"]}

    rows: list[dict[str, Any]] = []
    for family in draft["families"]:
        family_id = family["id"]
        if family_id not in pilot_families or family_id not in pairs:
            raise ValueError(f"missing pilot or pair evidence for {family_id}")
        implemented = pilot_families[family_id]
        pair = pairs[family_id]
        target_parts = _target_parts(family["failure_target"])
        mechanisms = [MECHANISM_BY_TARGET[target] for target in target_parts]
        diagnostics = list(
            dict.fromkeys(metric for item in mechanisms for metric in item["diagnostics"])
        )
        rows.append(
            {
                "family_index": family["family_index"],
                "family": family_id,
                "failure_target": family["failure_target"],
                "implemented_mechanism": implemented["implemented_mechanism"],
                "prototype_limitation": implemented.get("limitation"),
                "pgrr_components_under_probe": list(
                    dict.fromkeys(
                        component for item in mechanisms for component in item["components"]
                    )
                ),
                "mechanism_questions": [item["question"] for item in mechanisms],
                "required_primary_metrics": PRIMARY_METRICS,
                "required_cost_metrics_on_joint_success": COST_METRICS,
                "required_mechanism_diagnostics": diagnostics,
                "development_observation": {
                    "scope": "single train-only pair; descriptive only",
                    "base_outcome": pair["base_outcome"],
                    "pgrr_outcome": pair["pgrr_outcome"],
                    "pgrr_recovery_triggered": pair["pgrr_recovery_triggered"] == "True",
                    "pgrr_decision_events": int(pair["pgrr_decision_events"]),
                    "pgrr_temporary_subgoals": int(pair["pgrr_temporary_subgoals"]),
                    "pgrr_original_goal_restores": int(
                        pair["pgrr_original_goal_restores"]
                    ),
                },
            }
        )

    return {
        "schema_version": 1,
        "scope": pilot["scope"],
        "benchmark_id": pilot["benchmark_id"],
        "comparison_methods": draft["comparison_protocol"]["methods"],
        "paired_by": draft["comparison_protocol"]["paired_by"],
        "paper_flow": [
            "scenario manipulation and seeded reset",
            "classical planner controls normal navigation",
            "failure signal triggers recovery only when needed",
            "PGRR selects WAIT/BACKUP/REPLAN/CONTINUE or one of 21 temporary subgoals",
            "classical planner executes the temporary goal",
            "original goal is restored and navigation rejoins",
            "report preserved outcome, joint-success costs, and mechanism diagnostics",
        ],
        "claim_boundary": pilot["claim_boundary"],
        "families": rows,
        "sources": {
            "draft": str(draft_path),
            "pilot": str(pilot_path),
            "development_pairs": str(pair_csv),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Eight-family algorithm-scenario-metric matrix",
        "",
        (
            "> Scope: train-only development evidence. This table does not "
            "establish superiority, generalization, or statistical significance."
        ),
        "",
        (
            "| # | Family | Target | PGRR components being probed | "
            "Primary diagnostics | Current descriptive pair |"
        ),
        "|---:|---|---|---|---|---|",
    ]
    for row in report["families"]:
        observation = row["development_observation"]
        lines.append(
            (
                "| {family_index} | `{family}` | {failure_target} | {components} | "
                "{diagnostics} | Base={base}; PGRR={pgrr} |"
            ).format(
                family_index=row["family_index"] + 1,
                family=row["family"],
                failure_target=row["failure_target"],
                components="; ".join(row["pgrr_components_under_probe"]),
                diagnostics="; ".join(row["required_mechanism_diagnostics"]),
                base=observation["base_outcome"],
                pgrr=observation["pgrr_outcome"],
            )
        )
    lines.extend(["", "## Paper flow", ""])
    lines.extend(
        f"{index}. {step}" for index, step in enumerate(report["paper_flow"], 1)
    )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            (
                "The current eight pairs are mechanism-development observations only. "
                "Primary outcomes must be reported for every episode; time, path "
                "length, and angular jerk are compared only on joint successes. "
                "Mechanism diagnostics explain where the pipeline activates or stalls "
                "but do not prove causality."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--draft",
        type=Path,
        default=Path("configs/experiments/pgrr_extension_v1_eight_family_draft.yaml"),
    )
    parser.add_argument(
        "--pilot",
        type=Path,
        default=Path("configs/experiments/pgrr_extension_v1_eight_family_pilot.yaml"),
    )
    parser.add_argument(
        "--pairs",
        type=Path,
        default=Path("outputs/student/eight_family_pilot/minimal_pair_summary.csv"),
    )
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    report = build_matrix(args.draft, args.pilot, args.pairs)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
