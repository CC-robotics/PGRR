#!/usr/bin/env python3
"""Summarize the bounded closing-gap v2 diagnosis and v3 fixed screen."""

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


def _event_complete(outcome: dict[str, Any]) -> bool:
    transitions: dict[str, list[str]] = {}
    for event in outcome.get("scenario_events", []):
        transitions.setdefault(event["actor_name"], []).append(event["transition"])
    return len(transitions) == 2 and all(
        value == ["pre_event_to_active_event", "active_event_to_released"]
        for value in transitions.values()
    )


def build_summary(v2_runtime: Path, v3_runtime: Path) -> dict[str, Any]:
    v2_pgrr = _load(
        v2_runtime / "pgrr_priority_closinggap_v2_train_s98200_pgrr.outcome.json"
    )
    base = _load(v3_runtime / "pgrr_priority_closinggap_v3_train_s98200_base.outcome.json")
    pgrr = _load(v3_runtime / "pgrr_priority_closinggap_v3_train_s98200_pgrr.outcome.json")
    recovery = summarize_recovery(
        v3_runtime / "pgrr_priority_closinggap_v3_train_s98200_pgrr.jsonl"
    )
    event_complete = _event_complete(pgrr)
    restored = recovery["original_goal_restored_event_count"] >= 1
    positive = base["outcome"] != "GOAL_REACHED" and pgrr["outcome"] == "GOAL_REACHED"
    return {
        "schema_version": 1,
        "scope": "train_only_single_seed_screen",
        "family": "closing_gap_multi_pedestrian",
        "selected_variant": "closing_gap_bounded_release_v3",
        "seed": 98200,
        "route_distance_m": 15.0,
        "episode_timeout_s": 90,
        "v2_diagnostic": {
            "pgrr_outcome": v2_pgrr["outcome"],
            "pgrr_physical_goal_distance_m": v2_pgrr["physical_goal_distance_m"],
            "interpretation": "terminal actor clearance 1.7 m caused repeated recovery",
        },
        "v3_change": {
            "only_behavioral_geometry_change": "actor terminal route clearance",
            "terminal_clearance_m": {"v2": 1.7, "v3": 3.5},
            "unchanged": [
                "seed",
                "route",
                "actor start positions",
                "actor speed",
                "trigger",
                "active duration",
                "timeout",
                "checkpoint",
                "algorithm thresholds",
            ],
        },
        "base": base,
        "pgrr": pgrr,
        "positive_pair": positive,
        "pgrr_event_chain_complete_for_both_actors": event_complete,
        "pgrr_original_goal_restored": restored,
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
        "eligible_for_train_replication": positive and event_complete and restored,
        "independent_validation_complete": False,
        "paper_claim_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v2-runtime", type=Path, required=True)
    parser.add_argument("--v3-runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = build_summary(args.v2_runtime, args.v3_runtime)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
