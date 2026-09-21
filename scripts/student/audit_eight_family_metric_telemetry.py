#!/usr/bin/env python3
"""Audit whether the eight-family study metrics are available from current telemetry."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

CATALOG: dict[str, dict[str, Any]] = {
    "GOAL_REACHED": {
        "status": "direct",
        "source_fields": ["outcome"],
        "evidence": "episode_logger_node.py outcome JSON",
    },
    "COLLISION": {
        "status": "direct",
        "source_fields": ["outcome"],
        "evidence": "episode_logger_node.py outcome JSON",
    },
    "TIMEOUT": {
        "status": "direct",
        "source_fields": ["outcome"],
        "evidence": "episode_logger_node.py outcome JSON",
    },
    "completion_time_s": {
        "status": "derivable",
        "source_fields": ["timestamp"],
        "evidence": "scripts/evaluate/collect_results.py episode_duration_s",
    },
    "path_length_m": {
        "status": "derivable",
        "source_fields": ["robot_pose", "privileged.robot_pose"],
        "evidence": "scripts/evaluate/collect_results.py _path_metrics",
    },
    "angular_jerk": {
        "status": "derivable",
        "source_fields": ["timestamp", "robot_velocity[1]"],
        "evidence": "scripts/evaluate/collect_results.py _angular_jerk",
        "canonical_output": "mean_abs_angular_jerk_rad_s3",
    },
    "triggered": {
        "status": "derivable",
        "source_fields": ["recovery_state", "recovery_action", "recovery_reason"],
        "evidence": "scripts/evaluate/collect_results.py recovery_trigger_count",
    },
    "time_to_first_recovery_s": {
        "status": "derivable",
        "source_fields": ["timestamp", "recovery_state"],
        "evidence": "first non-normal recovery-state timestamp minus episode start",
    },
    "minimum_clearance_m": {
        "status": "definition_required",
        "source_fields": ["nearest_obstacle_distance", "privileged.nearest_human_distance"],
        "evidence": (
            "both obstacle and human distances are logged, but the paper metric "
            "must choose one definition"
        ),
        "required_decision": (
            "define clearance as obstacle clearance, human clearance, or report both"
        ),
    },
    "recovery_cycle_count": {
        "status": "derivable",
        "source_fields": ["recovery_state"],
        "evidence": "scripts/student/diagnose_eight_family_recovery_progress.py",
    },
    "action_switch_count": {
        "status": "derivable",
        "source_fields": ["recovery_action"],
        "evidence": "count adjacent action-ID changes within recovery cycles",
    },
    "cycle_progress_m": {
        "status": "derivable",
        "source_fields": ["goal", "robot_pose", "recovery_state"],
        "evidence": (
            "scripts/student/diagnose_eight_family_recovery_progress.py "
            "original_goal_progress_m"
        ),
    },
    "stationary_duration_s": {
        "status": "derivable",
        "source_fields": ["timestamp", "robot_velocity[0]"],
        "evidence": "integrate intervals below a declared linear-speed threshold",
        "required_parameter": "stationary linear-speed threshold",
    },
    "goal_restore_count": {
        "status": "derivable",
        "source_fields": ["recovery_reason"],
        "evidence": "count original_goal_restored transitions",
    },
    "deadlock_duration_s": {
        "status": "definition_required",
        "source_fields": ["timestamp", "robot_velocity", "distance_to_goal", "recovery_state"],
        "evidence": "inputs exist, but no agreed deadlock onset/clearance contract is checked in",
        "required_decision": (
            "define speed, progress-window, hazard, and minimum-duration conditions"
        ),
    },
    "temporary_subgoal_count": {
        "status": "derivable",
        "source_fields": ["recovery_action"],
        "evidence": "count decision transitions with action IDs 0 through 20",
    },
    "planner_failure_count": {
        "status": "derivable",
        "source_fields": ["planner_status", "outcome"],
        "evidence": (
            "count planner-status failure entries; terminal outcome preserves "
            "PLANNER_FAILURE"
        ),
    },
    "replan_count": {
        "status": "derivable",
        "source_fields": ["recovery_action"],
        "evidence": "count decision transitions with REPLAN action ID 23",
    },
    "rapid_retrigger_count": {
        "status": "derivable",
        "source_fields": ["timestamp", "recovery_state"],
        "evidence": "scripts/student/adapt_recovery_cycles_to_progress_contract.py",
        "required_parameter": "preregistered rapid-retrigger window",
    },
    "final_goal_distance_m": {
        "status": "direct_and_derivable",
        "source_fields": [
            "localized_goal_distance_m",
            "physical_goal_distance_m",
            "goal",
            "robot_pose",
        ],
        "evidence": "outcome JSON plus raw-log geometric reconstruction",
    },
}


def build_audit(matrix: dict[str, Any]) -> dict[str, Any]:
    usages: dict[str, set[str]] = {}
    groups: dict[str, set[str]] = {}
    for family in matrix["families"]:
        name = family["family"]
        for group_name, key in (
            ("primary", "required_primary_metrics"),
            ("joint_success_cost", "required_cost_metrics_on_joint_success"),
            ("mechanism", "required_mechanism_diagnostics"),
        ):
            for metric in family[key]:
                usages.setdefault(metric, set()).add(name)
                groups.setdefault(metric, set()).add(group_name)

    unknown = sorted(set(usages) - set(CATALOG))
    if unknown:
        raise ValueError(f"metrics missing from telemetry catalog: {unknown}")

    rows = []
    for metric in sorted(usages):
        row = {
            "metric": metric,
            "groups": sorted(groups[metric]),
            "families": sorted(usages[metric]),
            **CATALOG[metric],
        }
        rows.append(row)
    counts = Counter(row["status"] for row in rows)
    return {
        "schema_version": 1,
        "benchmark_id": matrix["benchmark_id"],
        "scope": "telemetry_design_audit_no_runtime_or_performance_claim",
        "claim_boundary": matrix["claim_boundary"],
        "metric_count": len(rows),
        "status_counts": dict(sorted(counts.items())),
        "metrics": rows,
        "blocking_definition_decisions": [
            row["metric"] for row in rows if row["status"] == "definition_required"
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Eight-family telemetry coverage audit",
        "",
        (
            "> Design audit only. It does not establish runtime success, superiority, "
            "generalization, or significance."
        ),
        "",
        "| Metric | Group | Status | Families | Source fields / remaining decision |",
        "|---|---|---|---:|---|",
    ]
    for row in report["metrics"]:
        detail = ", ".join(row["source_fields"])
        if row.get("required_decision"):
            detail += f"; DECIDE: {row['required_decision']}"
        if row.get("required_parameter"):
            detail += f"; preregister: {row['required_parameter']}"
        lines.append(
            f"| `{row['metric']}` | {', '.join(row['groups'])} | "
            f"**{row['status']}** | {len(row['families'])} | {detail} |"
        )
    lines.extend(
        [
            "",
            "## Result",
            "",
            f"The matrix requests {report['metric_count']} unique metrics. "
            f"Two still require an operational definition: "
            f"{', '.join(report['blocking_definition_decisions'])}. "
            "All other requested metrics are directly logged or derivable from the current schema. "
            "Derivable does not mean already computed for every future run; raw "
            "artifacts must still be preserved.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    matrix = json.loads(args.matrix.read_text(encoding="utf-8"))
    report = build_audit(matrix)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report["status_counts"], sort_keys=True))


if __name__ == "__main__":
    main()
