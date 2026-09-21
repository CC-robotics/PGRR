#!/usr/bin/env python3
"""Compile one open-geometry, train-only closing-gap event candidate."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from types import ModuleType
from typing import Any

from ramp_core.scenario import ScenarioEventController

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "outputs/student/event_controlled_candidates"
SEED = 91410
SCENARIO_ID = f"closing_gap_open_release_v1_train_r00_s{SEED}"


def _module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base() -> ModuleType:
    return _module("closing_gap_base", ROOT / "scripts/data/compile_scenarios.py")


def _display(path: Path) -> str:
    try:
        path = path.relative_to(ROOT)
    except ValueError:
        pass
    return str(path).replace("\\", "/")


def _actor(
    *, name: str, actor_id: int, start: list[float], goal: list[float]
) -> dict[str, Any]:
    yaw = math.atan2(goal[1] - start[1], goal[0] - start[0])
    start_pose = [start[0], start[1], yaw]
    goal_pose = [goal[0], goal[1], yaw]
    return {
        "name": name,
        "id": actor_id,
        "pos": start_pose,
        "type": "adult",
        "model": "gazebo_actor",
        "waypoints": [start_pose, goal_pose],
        "max_vel": 0.45,
        "radius": 0.35,
        "robot_avoidance_distance_m": 0.8,
        "cyclic_goals": False,
        "goal_radius": 0.3,
        "behavior": _base()._behavior(),
    }


def compile_candidate(output_root: Path) -> dict[str, Any]:
    """Materialize one fixed train candidate without validation or test rows."""

    actors = [
        _actor(name="ped_00", actor_id=1, start=[14.25, 8.5], goal=[14.25, 15.5]),
        _actor(name="ped_01", actor_id=2, start=[15.75, 15.5], goal=[15.75, 8.5]),
    ]
    events = []
    for actor in actors:
        events.append(
            {
                "event_id": f"closing_gap_release_{actor['name']}_v1_train",
                "actor_name": actor["name"],
                "trigger_metric": "robot_actor_distance_below",
                "trigger_threshold_m": 5.0,
                "trigger_hysteresis_m": 0.25,
                "active_duration_s": 20.0,
                "commands": {
                    "pre_event": "hold_at_start",
                    "active_event": "release_actor_on_noncyclic_crossing",
                    "released": "resume_noncyclic_route",
                },
            }
        )
    event_mapping = {"schema_version": 1, "events": events}
    ScenarioEventController.from_mapping(
        event_mapping, actor_names={actor["name"] for actor in actors}
    )
    payload = {
        "ramp_metadata": {
            "schema_version": 1,
            "benchmark_id": "pgrr_extension_event_candidates_v1",
            "scenario_id": SCENARIO_ID,
            "family": "closing_gap_multi_pedestrian",
            "variant_id": "closing_gap_open_release_v1",
            "density": "medium",
            "split": "train",
            "seed": SEED,
            "replicate": 0,
            "map_id": "map_empty",
            "candidate_status": "train_only_pre_runtime_validation",
            "paired_methods": ["base", "pgrr"],
            "event_control_required": True,
            "assigned_variables": {
                "actor_speed_mps": 0.45,
                "trigger_distance_m": 5.0,
                "crossing_x_m": [14.25, 15.75],
                "terminal_route_clearance_m": 3.5,
                "static_obstacle_count": 0,
            },
        },
        "ramp_event_control": event_mapping,
        "robots": [{"start": [5.0, 12.0, 0.0], "goal": [27.0, 12.0, 0.0]}],
        "obstacles": {"static": [], "interactive": [], "dynamic": actors},
    }
    bounds = [0.0, 30.0, 0.0, 24.0]
    base = _base()
    base._validate_scenario(payload, bounds)
    destination = output_root / "generated/arena/map_empty" / f"{SCENARIO_ID}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    destination.write_text(text, encoding="utf-8")
    preview = output_root / "previews" / f"{SCENARIO_ID}.png"
    preview.parent.mkdir(parents=True, exist_ok=True)
    base._render_preview(payload, bounds, 0.05, preview)
    report = {
        "candidate_id": SCENARIO_ID,
        "family": "closing_gap_multi_pedestrian",
        "split": "train",
        "seed": SEED,
        "held_out_test_materialized": False,
        "paired_methods_share_one_scenario": True,
        "event_mapping_valid": True,
        "actor_count": len(actors),
        "actor_routes_noncyclic": all(not actor["cyclic_goals"] for actor in actors),
        "static_obstacle_count": 0,
        "terminal_route_clearance_m": 3.5,
        "scenario_path": _display(destination),
        "preview_path": _display(preview),
        "scenario_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "runtime_executed": False,
    }
    manifest = output_root / "closing_gap_open_release_v1_train_manifest.json"
    manifest.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(compile_candidate(args.output_root.resolve()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
