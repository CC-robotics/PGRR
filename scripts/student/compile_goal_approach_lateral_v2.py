#!/usr/bin/env python3
"""Compile the <=15 m one-shot goal-approach lateral candidate."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml
from ramp_core.action_space import ACTIONS, RecoveryActionKind
from ramp_core.scenario import ScenarioEventController
from ramp_core.types import Pose2D

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = (
    ROOT / "configs/experiments/pgrr_goal_approach_lateral_v2_train_r00.yaml"
)
DEFAULT_OUTPUT = ROOT / "outputs/student/goal_approach_lateral_v2_screen"


def _module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _base() -> ModuleType:
    return _module("goal_approach_v2_base", ROOT / "scripts/data/compile_scenarios.py")


def load_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("benchmark_id") != "pgrr_priority_four_optimization_v1":
        raise ValueError("unexpected benchmark_id")
    if config.get("family") != "goal_approach_lateral_interruption":
        raise ValueError("unexpected family")
    split = config.get("split", {})
    split_name = split.get("name")
    expected_status = {
        "train": "train_only_single_seed_screen",
        "validation": "independent_validation",
    }
    if split_name not in expected_status:
        raise ValueError("only train or validation compilation is allowed")
    if config.get("status") != expected_status[split_name]:
        raise ValueError("status does not match the requested split")
    if split.get("held_out_test_enabled") is not False:
        raise ValueError("test materialization is forbidden")
    start = config["robot"]["start"]
    goal = config["robot"]["goal"]
    distance = math.dist(start[:2], goal[:2])
    if distance > float(config["screening"]["maximum_start_goal_distance_m"]):
        raise ValueError("start-goal distance exceeds the configured maximum")
    return config


def build_scenario(config: dict[str, Any]) -> dict[str, Any]:
    base = _base()
    actor_config = config["actor"]
    x = float(actor_config["crossing_x_m"])
    y0 = float(actor_config["start_y_m"])
    y1 = float(actor_config["terminal_y_m"])
    yaw = math.atan2(y1 - y0, 0.0)
    actor = {
        "name": str(actor_config["name"]),
        "id": 1,
        "pos": [x, y0, yaw],
        "type": "adult",
        "model": "gazebo_actor",
        "waypoints": [[x, y0, yaw], [x, y1, yaw]],
        "max_vel": float(actor_config["speed_mps"]),
        "radius": float(actor_config["radius_m"]),
        "robot_avoidance_distance_m": float(
            actor_config["robot_avoidance_distance_m"]
        ),
        "cyclic_goals": False,
        "goal_radius": 0.3,
        "behavior": base._behavior(),
    }
    event_config = config["event"]
    event_mapping = {
        "schema_version": 1,
        "events": [
            {
                "event_id": "goal_approach_lateral_one_shot_v2_train",
                "actor_name": actor["name"],
                "trigger_metric": event_config["trigger_metric"],
                "trigger_threshold_m": float(event_config["trigger_threshold_m"]),
                "trigger_hysteresis_m": float(event_config["trigger_hysteresis_m"]),
                "active_duration_s": float(event_config["active_duration_s"]),
                "commands": dict(event_config["commands"]),
            }
        ],
    }
    ScenarioEventController.from_mapping(event_mapping, actor_names={actor["name"]})
    split = config["split"]
    payload = {
        "ramp_metadata": {
            "schema_version": 1,
            "benchmark_id": config["benchmark_id"],
            "scenario_id": config["output"]["scenario_id"],
            "family": config["family"],
            "variant_id": config["variant_id"],
            "density": "low",
            "split": str(split["name"]),
            "seed": int(split["seed"]),
            "replicate": int(split["replicate"]),
            "map_id": config["map"]["id"],
            "candidate_status": (
                "train_only_pre_runtime_screen"
                if split["name"] == "train"
                else "independent_validation_pre_runtime"
            ),
            "event_control_required": True,
            "paired_methods": ["base", "pgrr"],
            "held_out_test_materialized": False,
        },
        "ramp_event_control": event_mapping,
        "robots": [
            {
                "start": [float(value) for value in config["robot"]["start"]],
                "goal": [float(value) for value in config["robot"]["goal"]],
            }
        ],
        "obstacles": {"static": [], "interactive": [], "dynamic": [actor]},
    }
    base._validate_scenario(payload, [float(value) for value in config["map"]["bounds_m"]])
    return payload


def audit_scenario(scenario: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    robot = scenario["robots"][0]
    actor = scenario["obstacles"]["dynamic"][0]
    start = tuple(float(value) for value in robot["start"][:2])
    goal = tuple(float(value) for value in robot["goal"][:2])
    crossing_x = float(actor["pos"][0])
    robot_y = float(start[1])
    route_distance = math.dist(start, goal)
    post_conflict_distance = goal[0] - crossing_x
    trigger_x = goal[0] - float(config["event"]["trigger_threshold_m"])
    nominal_trigger_time = (trigger_x - start[0]) / float(
        config["robot"]["nominal_screen_speed_mps"]
    )
    actor_center_eta = abs(robot_y - float(actor["pos"][1])) / float(actor["max_vel"])
    robot_intersection_eta = (crossing_x - trigger_x) / float(
        config["robot"]["nominal_screen_speed_mps"]
    )
    nominal_interaction_time = nominal_trigger_time + max(
        actor_center_eta, robot_intersection_eta
    )
    desired_start, desired_end = (
        float(value) for value in config["screening"]["desired_interaction_time_s"]
    )
    tolerance = float(config["screening"]["interaction_time_tolerance_s"])
    terminal_clearance = abs(float(actor["waypoints"][-1][1]) - robot_y)
    representative_pose = Pose2D(crossing_x - 1.0, robot_y, 0.0)
    bounds = [float(value) for value in config["map"]["bounds_m"]]
    static_subgoal_count = 0
    for action in ACTIONS:
        if action.kind is not RecoveryActionKind.SUBGOAL:
            continue
        target = action.target_pose(representative_pose)
        assert target is not None
        if bounds[0] <= target.x <= bounds[1] and bounds[2] <= target.y <= bounds[3]:
            static_subgoal_count += 1
    checks = {
        "allowed_non_test_split": scenario["ramp_metadata"]["split"]
        in {"train", "validation"},
        "held_out_test_not_materialized": scenario["ramp_metadata"][
            "held_out_test_materialized"
        ]
        is False,
        "route_within_15m": route_distance
        <= float(config["screening"]["maximum_start_goal_distance_m"]),
        "post_conflict_segment_sufficient": post_conflict_distance
        >= float(config["screening"]["minimum_post_conflict_distance_m"]),
        "event_is_one_shot": actor["cyclic_goals"] is False,
        "terminal_clears_robot_route": terminal_clearance
        >= float(config["screening"]["minimum_terminal_route_clearance_m"]),
        "nominal_interaction_in_target_window": desired_start - tolerance
        <= nominal_interaction_time
        <= desired_end + tolerance,
        "temporal_conflict_plausible": abs(actor_center_eta - robot_intersection_eta)
        <= 1.0,
        "static_subgoal_space_sufficient": static_subgoal_count
        >= int(config["screening"]["minimum_static_subgoal_count"]),
    }
    return {
        "schema_version": 1,
        "scenario_id": scenario["ramp_metadata"]["scenario_id"],
        "seed": scenario["ramp_metadata"]["seed"],
        "split": scenario["ramp_metadata"]["split"],
        "checks": checks,
        "ready_for_single_seed_runtime_pair": all(checks.values()),
        "route_distance_m": route_distance,
        "post_conflict_distance_m": post_conflict_distance,
        "nominal_trigger_time_s": nominal_trigger_time,
        "nominal_interaction_time_s": nominal_interaction_time,
        "actor_center_eta_after_trigger_s": actor_center_eta,
        "robot_intersection_eta_after_trigger_s": robot_intersection_eta,
        "terminal_route_clearance_m": terminal_clearance,
        "static_subgoal_count": static_subgoal_count,
        "interpretation": "offline gate only; not a simulator result or paper claim",
    }


def compile_candidate(config_path: Path, output_root: Path) -> dict[str, Any]:
    config = load_config(config_path)
    scenario = build_scenario(config)
    scenario_id = scenario["ramp_metadata"]["scenario_id"]
    destination = output_root / "generated/arena/map_empty" / f"{scenario_id}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(scenario, indent=2, sort_keys=True) + "\n"
    destination.write_text(text, encoding="utf-8")
    preview = output_root / "previews" / f"{scenario_id}.png"
    preview.parent.mkdir(parents=True, exist_ok=True)
    _base()._render_preview(
        scenario,
        [float(value) for value in config["map"]["bounds_m"]],
        float(config["map"]["preview_resolution_m"]),
        preview,
    )
    report = audit_scenario(scenario, config)
    report.update(
        {
            "scenario_path": str(destination.resolve()),
            "preview_path": str(preview.resolve()),
            "scenario_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "source_config": str(config_path.resolve()),
        }
    )
    (output_root / "offline_preflight.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(
        json.dumps(
            compile_candidate(args.config.resolve(), args.output_root.resolve()),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
