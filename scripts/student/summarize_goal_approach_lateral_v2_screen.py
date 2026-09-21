#!/usr/bin/env python3
"""Summarize the fixed goal-approach v2 single-seed screen."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .analyze_recovery_trace import summarize_recovery
except ImportError:
    from analyze_recovery_trace import summarize_recovery


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_summary(runtime: Path) -> dict[str, Any]:
    failed = _load(runtime / "pgrr_priority_goalapproach_v2_train_s97100_base.outcome.json")
    base = _load(
        runtime
        / "pgrr_priority_goalapproach_v2_train_s97100_base_retry01.outcome.json"
    )
    pgrr = _load(runtime / "pgrr_priority_goalapproach_v2_train_s97100_pgrr.outcome.json")
    if failed["outcome"] != "SIMULATOR_FAILURE" or failed["sample_count"] != 0:
        raise ValueError("expected preserved zero-sample Base infrastructure attempt")
    if base["sample_count"] <= 0 or pgrr["sample_count"] <= 0:
        raise ValueError("selected screen episodes must contain samples")
    recovery = summarize_recovery(
        runtime / "pgrr_priority_goalapproach_v2_train_s97100_pgrr.jsonl"
    )
    pgrr_transitions = [event["transition"] for event in pgrr["scenario_events"]]
    return {
        "schema_version": 1,
        "scope": "train_only_single_seed_screen",
        "family": "goal_approach_lateral_interruption",
        "scenario_id": "goal_approach_lateral_one_shot_v2_train_r00_s97100",
        "seed": 97100,
        "route_distance_m": 15.0,
        "base": base,
        "pgrr": pgrr,
        "preserved_infrastructure_attempt": failed,
        "positive_pair": base["outcome"] != "GOAL_REACHED"
        and pgrr["outcome"] == "GOAL_REACHED",
        "event_chain_complete_for_pgrr": pgrr_transitions
        == ["pre_event_to_active_event", "active_event_to_released"],
        "pgrr_event_transitions": pgrr["scenario_events"],
        "pgrr_recovery": {
            "state_transitions": recovery["state_transitions"],
            "decision_action_counts": recovery["decision_action_counts"],
            "temporary_subgoal_decision_count": recovery[
                "temporary_subgoal_decision_count"
            ],
            "original_goal_restored_event_count": recovery[
                "original_goal_restored_event_count"
            ],
        },
        "eligible_for_train_replication": (
            base["outcome"] != "GOAL_REACHED"
            and pgrr["outcome"] == "GOAL_REACHED"
            and pgrr_transitions
            == ["pre_event_to_active_event", "active_event_to_released"]
            and recovery["original_goal_restored_event_count"] >= 1
        ),
        "independent_validation_complete": False,
        "paper_claim_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = build_summary(args.runtime)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
