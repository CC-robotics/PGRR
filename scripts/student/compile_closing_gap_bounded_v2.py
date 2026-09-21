#!/usr/bin/env python3
"""Compile the bounded <=15 m two-pedestrian closing-gap v2 candidate."""

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
DEFAULT_CONFIG = ROOT / "configs/experiments/pgrr_closing_gap_bounded_v2_train_r00.yaml"
DEFAULT_OUTPUT = ROOT / "outputs/student/closing_gap_bounded_v2_screen"


def _module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _base() -> ModuleType:
    return _module("closing_gap_v2_base", ROOT / "scripts/data/compile_scenarios.py")


def load_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("benchmark_id") != "pgrr_priority_four_optimization_v1":
        raise ValueError("unexpected benchmark_id")
    if config.get("status") != "train_only_single_seed_screen":
        raise ValueError("candidate must remain a train-only screen")
    if config.get("family") != "closing_gap_multi_pedestrian":
        raise ValueError("unexpected family")
    split = config.get("split", {})
    if split.get("name") != "train" or split.get("held_out_test_enabled") is not False:
        raise ValueError("test materialization is forbidden")
    if len(config["actors"]["definitions"]) != 2:
        raise ValueError("bounded closing-gap requires exactly two actors")
    return config


def build_scenario(config: dict[str, Any]) -> dict[str, Any]:
    base = _base()
    common = config["actors"]
    actors = []
    events = []
    for definition in common["definitions"]:
        x = float(definition["crossing_x_m"])
        y0 = float(definition["start_y_m"])
        y1 = float(definition["terminal_y_m"])
        yaw = math.atan2(y1 - y0, 0.0)
        actor = {
            "name": str(definition["name"]),
            "id": int(definition["id"]),
            "pos": [x, y0, yaw],
            "type": "adult",
            "model": "gazebo_actor",
            "waypoints": [[x, y0, yaw], [x, y1, yaw]],
            "max_vel": float(common["speed_mps"]),
            "radius": float(common["radius_m"]),
            "robot_avoidance_distance_m": float(
                common["robot_avoidance_distance_m"]
            ),
            "cyclic_goals": False,
            "goal_radius": 0.3,
            "behavior": base._behavior(),
        }
        actors.append(actor)
        event = config["event"]
        events.append(
            {
                "event_id": (
                    f"closing_gap_bounded_{actor['name']}_"
                    f"{event.get('id_version', 'v2')}_train"
                ),
                "actor_name": actor["name"],
                "trigger_metric": event["trigger_metric"],
                "trigger_threshold_m": float(event["trigger_threshold_m"]),
                "trigger_hysteresis_m": float(event["trigger_hysteresis_m"]),
                "active_duration_s": float(event["active_duration_s"]),
                "commands": dict(event["commands"]),
            }
        )
    event_mapping = {"schema_version": 1, "events": events}
    ScenarioEventController.from_mapping(
        event_mapping, actor_names={actor["name"] for actor in actors}
    )
    split = config["split"]
    scenario = {
        "ramp_metadata": {
            "schema_version": 1,
            "benchmark_id": config["benchmark_id"],
            "scenario_id": config["output"]["scenario_id"],
            "family": config["family"],
            "variant_id": config["variant_id"],
            "density": "medium",
            "split": "train",
            "seed": int(split["seed"]),
            "replicate": int(split["replicate"]),
            "map_id": config["map"]["id"],
            "candidate_status": "train_only_pre_runtime_screen",
            "event_control_required": True,
            "paired_methods": ["base", "pgrr"],
            "held_out_test_materialized": False,
        },
        "ramp_event_control": event_mapping,
        "robots": [{"start": config["robot"]["start"], "goal": config["robot"]["goal"]}],
        "obstacles": {"static": [], "interactive": [], "dynamic": actors},
    }
    base._validate_scenario(scenario, config["map"]["bounds_m"])
    return scenario


def audit_scenario(scenario: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    robot = scenario["robots"][0]
    start = tuple(float(value) for value in robot["start"][:2])
    goal = tuple(float(value) for value in robot["goal"][:2])
    actors = scenario["obstacles"]["dynamic"]
    route_distance = math.dist(start, goal)
    mean_crossing_x = sum(float(actor["pos"][0]) for actor in actors) / len(actors)
    post_conflict_distance = goal[0] - mean_crossing_x
    trigger_x = goal[0] - float(config["event"]["trigger_threshold_m"])
    nominal_trigger_time = (trigger_x - start[0]) / float(
        config["robot"]["nominal_screen_speed_mps"]
    )
    center_times = [
        abs(start[1] - float(actor["pos"][1])) / float(actor["max_vel"])
        for actor in actors
    ]
    robot_intersection_eta = (mean_crossing_x - trigger_x) / float(
        config["robot"]["nominal_screen_speed_mps"]
    )
    interaction_time = nominal_trigger_time + max(max(center_times), robot_intersection_eta)
    desired_start, desired_end = map(
        float, config["screening"]["desired_interaction_time_s"]
    )
    tolerance = float(config["screening"]["interaction_time_tolerance_s"])
    active_duration = float(config["event"]["active_duration_s"])
    duration_min, duration_max = map(
        float, config["screening"]["active_duration_range_s"]
    )
    terminal_clearances = [
        abs(float(actor["waypoints"][-1][1]) - start[1]) for actor in actors
    ]
    bounds = [float(value) for value in config["map"]["bounds_m"]]
    representative = Pose2D(mean_crossing_x - 1.0, start[1], 0.0)
    static_subgoal_count = sum(
        1
        for action in ACTIONS
        if action.kind is RecoveryActionKind.SUBGOAL
        and (target := action.target_pose(representative)) is not None
        and bounds[0] <= target.x <= bounds[1]
        and bounds[2] <= target.y <= bounds[3]
    )
    checks = {
        "train_only": scenario["ramp_metadata"]["split"] == "train",
        "held_out_test_not_materialized": scenario["ramp_metadata"][
            "held_out_test_materialized"
        ]
        is False,
        "route_within_15m": route_distance
        <= float(config["screening"]["maximum_start_goal_distance_m"]),
        "post_conflict_segment_sufficient": post_conflict_distance
        >= float(config["screening"]["minimum_post_conflict_distance_m"]),
        "active_duration_bounded": duration_min <= active_duration <= duration_max,
        "actors_release_synchronously": len(
            {event["trigger_metric"] for event in scenario["ramp_event_control"]["events"]}
        )
        == 1,
        "actor_center_times_aligned": max(center_times) - min(center_times)
        <= float(config["screening"]["maximum_actor_center_time_difference_s"]),
        "release_near_narrowest_gap": max(
            abs(value - active_duration) for value in center_times
        )
        <= 0.25,
        "temporal_conflict_plausible": abs(max(center_times) - robot_intersection_eta)
        <= 1.0,
        "interaction_in_target_window": desired_start - tolerance
        <= interaction_time
        <= desired_end + tolerance,
        "terminal_positions_clear_route": min(terminal_clearances)
        >= float(config["screening"]["minimum_terminal_route_clearance_m"]),
        "actors_noncyclic": all(not actor["cyclic_goals"] for actor in actors),
        "static_subgoal_space_sufficient": static_subgoal_count
        >= int(config["screening"]["minimum_static_subgoal_count"]),
    }
    return {
        "schema_version": 1,
        "scenario_id": scenario["ramp_metadata"]["scenario_id"],
        "seed": scenario["ramp_metadata"]["seed"],
        "split": "train",
        "checks": checks,
        "ready_for_single_seed_runtime_pair": all(checks.values()),
        "route_distance_m": route_distance,
        "post_conflict_distance_m": post_conflict_distance,
        "active_duration_s": active_duration,
        "actor_center_eta_after_trigger_s": center_times,
        "robot_intersection_eta_after_trigger_s": robot_intersection_eta,
        "nominal_interaction_time_s": interaction_time,
        "terminal_route_clearance_m": terminal_clearances,
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
            "source_config": str(config_path),
            "scenario_path": str(destination),
            "preview_path": str(preview),
            "scenario_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        }
    )
    manifest = output_root / "closing_gap_bounded_v2_train_manifest.json"
    manifest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = compile_candidate(args.config.resolve(), args.output_root.resolve())
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
