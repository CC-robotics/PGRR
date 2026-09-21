#!/usr/bin/env python3
"""Validate the non-executable train/validation event-control contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

EXPECTED_PHASES = ["pre_event", "active_event", "released"]
EXPECTED_CHECKS = {
    "event_triggered_exactly_once",
    "active_phase_duration_within_tolerance",
    "release_observed_before_episode_end",
    "actor_clears_robot_path_after_release",
    "base_and_pgrr_receive_identical_event_contract",
    "task_has_a_collision_free_post_release_route",
    "policy_observation_contains_no_event_controller_state",
}
EXPECTED_FAMILIES = {
    "lead_pedestrian_sudden_stop",
    "goal_approach_lateral_interruption",
}


def validate(config: dict[str, Any]) -> dict[str, Any]:
    errors = []
    if config.get("status") != "draft_train_validation_only_non_executable":
        errors.append("contract status must remain non-executable")
    boundary = config.get("claim_boundary", {})
    if boundary.get("allowed_splits") != ["train", "validation"]:
        errors.append("only ordered train/validation splits are allowed")
    if boundary.get("held_out_test_materialized") is not False:
        errors.append("held-out test materialization must remain false")
    if boundary.get("algorithm_threshold_change_authorized") is not False:
        errors.append("threshold changes must remain unauthorized")
    if boundary.get("policy_retraining_authorized") is not False:
        errors.append("policy retraining must remain unauthorized")
    if boundary.get("privileged_event_state_enters_policy_observation") is not False:
        errors.append("event-controller state must not enter policy observations")
    if config.get("required_event_phases") != EXPECTED_PHASES:
        errors.append("event phases must be pre_event, active_event, released")
    checks = set(config.get("required_acceptance_checks", []))
    if checks != EXPECTED_CHECKS:
        errors.append("acceptance-check set is incomplete or contains unknown checks")
    variants = config.get("variants", [])
    families = {variant.get("family") for variant in variants}
    if families != EXPECTED_FAMILIES or len(variants) != 2:
        errors.append("exactly the two anchor families must be specified")
    seeds = []
    for variant in variants:
        for split in ("train", "validation"):
            split_config = variant.get(split, {})
            seed = split_config.get("seed")
            if not isinstance(seed, int):
                errors.append(f"{variant.get('family')} {split} seed must be an integer")
            else:
                seeds.append(seed)
        trigger = variant.get("trigger", {})
        active = variant.get("active_event", {})
        release = variant.get("release", {})
        if float(trigger.get("threshold_m", 0.0)) <= 0.0:
            errors.append(f"{variant.get('family')} trigger threshold must be positive")
        if float(active.get("duration_s", 0.0)) <= 0.0:
            errors.append(f"{variant.get('family')} active duration must be positive")
        if release.get("terminal_waypoint_off_robot_centerline") is not True:
            errors.append(f"{variant.get('family')} release must clear the robot path")
        if not variant.get("forbidden_shortcut"):
            errors.append(f"{variant.get('family')} must name its forbidden shortcut")
    if len(seeds) != len(set(seeds)):
        errors.append("train/validation seeds must be globally distinct")
    fairness = config.get("fairness", {})
    missing_fairness = sorted(key for key, value in fairness.items() if value is not True)
    if missing_fairness:
        errors.append(f"fairness flags must all be true: {missing_fairness}")
    return {
        "contract_id": config.get("contract_id"),
        "valid": not errors,
        "errors": errors,
        "variant_count": len(variants),
        "allowed_splits": boundary.get("allowed_splits"),
        "held_out_test_materialized": boundary.get("held_out_test_materialized"),
        "runtime_implementation_present": False,
        "executable_scenarios_generated": False,
        "next_gate": "implement_and_unit_test_event_state_machine_without_policy_leakage",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    report = validate(config)
    if not report["valid"]:
        raise SystemExit("; ".join(report["errors"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
