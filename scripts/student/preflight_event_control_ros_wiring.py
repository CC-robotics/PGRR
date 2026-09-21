#!/usr/bin/env python3
"""Inventory the exact default-off ROS wiring needed by scenario events."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SOURCE_PATHS = {
    "actor_controller": Path(
        "ros_ws/src/ramp_ros/ramp_ros/nodes/scenario_actor_controller_node.py"
    ),
    "episode_logger": Path("ros_ws/src/ramp_ros/ramp_ros/nodes/episode_logger_node.py"),
    "runtime_launcher": Path("scripts/arena/run_baseline_episode_inner.sh"),
    "event_core": Path("packages/ramp_core/ramp_core/scenario/events.py"),
    "event_adapter": Path("packages/ramp_core/ramp_core/scenario/contract.py"),
    "event_runtime": Path("packages/ramp_core/ramp_core/scenario/runtime.py"),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(root: Path) -> dict[str, Any]:
    paths = {name: root / relative for name, relative in SOURCE_PATHS.items()}
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise ValueError(f"missing source files: {missing}")
    text = {name: path.read_text(encoding="utf-8") for name, path in paths.items()}
    existing = {
        "actor_controller_launched": "scenario_actor_controller" in text["runtime_launcher"],
        "scenario_file_parameter_exists": (
            'declare_parameter("scenario_file", "")' in text["actor_controller"]
        ),
        "actual_robot_pose_available": "self._actual_robot_pose" in text["actor_controller"],
        "route_clock_available": "self._route_elapsed" in text["actor_controller"],
        "task_reset_callback_exists": "def _on_task_reset(" in text["actor_controller"],
        "event_core_exists": "class EventStateMachine" in text["event_core"],
        "event_contract_adapter_exists": "def event_spec_from_contract(" in text["event_adapter"],
        "event_runtime_adapter_exists": "class ScenarioEventController" in text["event_runtime"],
    }
    wiring = {
        "default_off_parameter": (
            'declare_parameter("enable_event_control", False)' in text["actor_controller"]
        ),
        "event_state_machine_imported": "ScenarioEventController" in text["actor_controller"],
        "event_contract_mapping_loaded": "ramp_event_control" in text["actor_controller"],
        "event_transition_topic_declared": "scenario_event_topic" in text["actor_controller"],
        "event_transition_logger_subscription": "scenario_event_topic" in text["episode_logger"],
        "event_enable_forwarded_by_launcher": "RAMP_ENABLE_EVENT_CONTROL" in text[
            "runtime_launcher"
        ],
    }
    required_changes = [
        {
            "order": 1,
            "component": "scenario JSON generator",
            "change": (
                "emit a validated ramp_event_control mapping only for new "
                "train/validation variants"
            ),
        },
        {
            "order": 2,
            "component": "scenario_actor_controller",
            "change": (
                "add enable_event_control=false and construct state machines only "
                "when enabled"
            ),
        },
        {
            "order": 3,
            "component": "scenario_actor_controller reset",
            "change": "reset event state together with route clocks on every task reset",
        },
        {
            "order": 4,
            "component": "scenario_actor_controller update",
            "change": (
                "apply commands after actual-pose freshness gates and fail closed "
                "on invalid state"
            ),
        },
        {
            "order": 5,
            "component": "event telemetry",
            "change": (
                "publish phase transitions with event id, simulation time, trigger "
                "metric, and command"
            ),
        },
        {
            "order": 6,
            "component": "episode_logger",
            "change": "record transition telemetry without exposing it to recovery observations",
        },
        {
            "order": 7,
            "component": "runtime launcher",
            "change": (
                "forward an opt-in environment flag; retain identical default "
                "behavior when unset"
            ),
        },
    ]
    return {
        "claim_boundary": "read-only source inventory; no ROS or simulator execution",
        "source_hashes": {
            name: {"path": str(SOURCE_PATHS[name]).replace("\\", "/"), "sha256": _sha256(path)}
            for name, path in paths.items()
        },
        "existing_prerequisites": existing,
        "existing_prerequisite_count": sum(existing.values()),
        "existing_prerequisite_total": len(existing),
        "runtime_wiring_checks": wiring,
        "runtime_wiring_present_count": sum(wiring.values()),
        "runtime_wiring_total": len(wiring),
        "ready_for_event_scenario_execution": all(wiring.values()),
        "default_behavior_changed": False,
        "required_changes": required_changes,
        "acceptance_after_wiring": [
            "legacy scenario source hashes preserve behavior with event flag unset",
            "event transitions reset deterministically across two synthetic episodes",
            "transition logger preserves one activation and one release",
            "event state is absent from recovery observation fields",
            "invalid or stale simulator pose prevents event advancement and reports "
            "unhealthy status",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = inspect(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "existing_prerequisites": (
                    f"{report['existing_prerequisite_count']}/"
                    f"{report['existing_prerequisite_total']}"
                ),
                "runtime_wiring": (
                    f"{report['runtime_wiring_present_count']}/"
                    f"{report['runtime_wiring_total']}"
                ),
                "ready_for_event_scenario_execution": report[
                    "ready_for_event_scenario_execution"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
