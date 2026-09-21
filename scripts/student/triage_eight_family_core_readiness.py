#!/usr/bin/env python3
"""Triage eight train-only scenario families before further PGRR tuning."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

FAILURES = {"COLLISION", "TIMEOUT", "PLANNER_FAILURE"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def classify(family: dict[str, Any], pair: dict[str, Any], root: Path) -> dict[str, Any]:
    scenario_path = root / family["scenario_path"]
    if not scenario_path.is_file():
        raise ValueError(f"missing scenario: {scenario_path}")
    if _sha256(scenario_path) != family["sha256"]:
        raise ValueError(f"scenario hash mismatch: {scenario_path}")
    if pair["family"] != family["id"] or pair["scenario_sha256"] != family["sha256"]:
        raise ValueError(f"pair does not match family: {family['id']}")
    base = pair["runs"]["base"]
    pgrr = pair["runs"]["pgrr"]
    limitation = str(family.get("limitation", ""))
    semantic_complete = not limitation
    base_is_challenging = base["outcome"] in FAILURES
    pgrr_goal_reached = pgrr["outcome"] == "GOAL_REACHED"
    trigger_observed = bool(pair["paired_interpretation"]["pgrr_recovery_triggered"])
    if not trigger_observed:
        next_gate = "trigger_or_scenario_activation_audit"
    elif not semantic_complete:
        next_gate = "event_semantics_and_task_feasibility"
    elif not pgrr_goal_reached:
        next_gate = "recovery_progress_and_candidate_availability"
    else:
        next_gate = "validation_replication"
    return {
        "family_index": family["family_index"],
        "family": family["id"],
        "scenario_id": family["scenario_id"],
        "hash_verified": True,
        "actual_motion_verified": bool(family["actual_motion_verified"]),
        "semantic_complete_for_named_event": semantic_complete,
        "limitation": limitation or None,
        "base_outcome": base["outcome"],
        "pgrr_outcome": pgrr["outcome"],
        "base_is_challenging": base_is_challenging,
        "pgrr_trigger_observed": trigger_observed,
        "pgrr_temporary_subgoal_decisions": int(
            pgrr.get("recovery_trace", {}).get("temporary_subgoal_decision_count", 0)
        ),
        "pgrr_goal_reached": pgrr_goal_reached,
        "core_comparative_ready": (
            semantic_complete
            and base_is_challenging
            and trigger_observed
            and pgrr_goal_reached
        ),
        "preserve_as_stress_diagnostic": True,
        "next_gate": next_gate,
    }


def analyze(config_path: Path, pair_root: Path, root: Path) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config.get("scope") != "train_only_development_not_final_evaluation":
        raise ValueError("triage accepts only train-only development pilots")
    rows = []
    for family in config["families"]:
        pair_path = pair_root / f"f{int(family['family_index']):02d}_{family['id']}.json"
        if not pair_path.is_file():
            raise ValueError(f"missing pair result: {pair_path}")
        pair = json.loads(pair_path.read_text(encoding="utf-8"))
        rows.append(classify(family, pair, root))
    next_gates = Counter(row["next_gate"] for row in rows)
    return {
        "benchmark_id": config["benchmark_id"],
        "claim_boundary": "eight single train-only development pairs; no held-out claims",
        "algorithm_change_authorized": False,
        "aggregate": {
            "family_count": len(rows),
            "hash_verified_count": sum(row["hash_verified"] for row in rows),
            "base_challenging_count": sum(row["base_is_challenging"] for row in rows),
            "pgrr_trigger_observed_count": sum(row["pgrr_trigger_observed"] for row in rows),
            "named_event_semantic_complete_count": sum(
                row["semantic_complete_for_named_event"] for row in rows
            ),
            "pgrr_goal_reached_count": sum(row["pgrr_goal_reached"] for row in rows),
            "core_comparative_ready_count": sum(row["core_comparative_ready"] for row in rows),
            "next_gate_counts": dict(sorted(next_gates.items())),
        },
        "families": rows,
        "recommendation": (
            "preserve all eight as development stress diagnostics; do not expand repeats yet. "
            "Repair semantic/activation gates and require train then validation goal-reaching "
            "before promoting a family into the core comparative set"
        ),
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    aggregate = report["aggregate"]
    lines = [
        "# Eight-family core-readiness triage",
        "",
        "## Boundary",
        "",
        report["claim_boundary"] + ".",
        "",
        "## Aggregate",
        "",
        f"- Scenario hashes verified: {aggregate['hash_verified_count']}/8",
        f"- Base challenging: {aggregate['base_challenging_count']}/8",
        f"- PGRR trigger observed: {aggregate['pgrr_trigger_observed_count']}/8",
        f"- Named-event semantics complete: {aggregate['named_event_semantic_complete_count']}/8",
        f"- PGRR goal reached: {aggregate['pgrr_goal_reached_count']}/8",
        f"- Core comparative ready: {aggregate['core_comparative_ready_count']}/8",
        "",
        "## Family triage",
        "",
        "| Family | Base | PGRR | Trigger | Semantics | Next gate |",
        "|---|---|---|---:|---:|---|",
    ]
    for row in report["families"]:
        lines.append(
            f"| `{row['family']}` | {row['base_outcome']} | {row['pgrr_outcome']} | "
            f"{row['pgrr_trigger_observed']} | {row['semantic_complete_for_named_event']} | "
            f"`{row['next_gate']}` |"
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            report["recommendation"] + ".",
            "",
            "No current family is discarded, and no current family is yet promoted as proof that",
            "PGRR succeeds where Base fails. This prevents multiplying repeats on structurally",
            "unhealthy prototypes while retaining every completed run as diagnostic evidence.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--pair-root", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.config, args.pair_root, args.root)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_markdown(report, args.markdown_output)
    print(json.dumps(report["aggregate"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
