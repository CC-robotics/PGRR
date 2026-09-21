#!/usr/bin/env python3
"""Compile and offline-screen one train-only crossing-flow anchor.

This script never starts ROS/Arena and never materializes a held-out test.  It
uses the frozen crossing-flow result only as a design prior, writes to
``outputs/student``, and produces explicit static, temporal, release, and
temporary-subgoal checks before any runtime pair is allowed.
"""

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
from ramp_core.types import Pose2D

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = (
    ROOT / "configs" / "experiments" / "pgrr_advantage_screen_crossing_v1.yaml"
)
DEFAULT_OUTPUT = ROOT / "outputs" / "student" / "advantage_scenario_screen"


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load helper module: {path}")
    module = importlib.util.module_from_spec(spec)
    # ``dataclasses`` resolves annotation metadata through ``sys.modules``
    # while the module body is executing.  Register dynamic helper modules
    # before execution just like Python's normal import machinery does.
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def _base_compiler() -> ModuleType:
    return _load_module(
        "pgrr_crossing_anchor_base_compiler",
        ROOT / "scripts" / "data" / "compile_scenarios.py",
    )


def _moderate_compiler() -> ModuleType:
    return _load_module(
        "pgrr_crossing_anchor_moderate_compiler",
        ROOT / "scripts" / "data" / "compile_moderate_benchmark.py",
    )


def load_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("crossing anchor config must be a mapping")
    if config.get("benchmark_id") != "pgrr_advantage_screen_v1":
        raise ValueError("unexpected benchmark_id")
    status = config.get("status")
    if status not in {"train_only_single_seed_screen", "validation_only_replication"}:
        raise ValueError("unexpected crossing anchor development status")
    split = config.get("split", {})
    split_name = split.get("name")
    if split_name not in {"train", "validation"} or split.get(
        "held_out_test_enabled"
    ) is not False:
        raise ValueError(
            "crossing anchor may materialize train only or validation; test is forbidden"
        )
    if status == "train_only_single_seed_screen" and split_name != "train":
        raise ValueError("train screen status requires the train split")
    if status == "validation_only_replication" and split_name != "validation":
        raise ValueError("validation status requires the validation split")
    family = config.get("family", {})
    if family.get("layout") != "crossing" or family.get("density") != "medium":
        raise ValueError("crossing anchor must remain a medium crossing-flow scenario")
    if int(family.get("pedestrian_count", 0)) != 2:
        raise ValueError("medium crossing anchor requires exactly two pedestrians")
    maximum_distance = config.get("screening", {}).get("maximum_start_goal_distance_m")
    if maximum_distance is not None:
        start = [float(value) for value in config["robot"]["start"]]
        goal = [float(value) for value in config["robot"]["goal"]]
        distance = math.hypot(goal[0] - start[0], goal[1] - start[1])
        if distance > float(maximum_distance) + 1.0e-9:
            raise ValueError("crossing anchor start-goal distance exceeds configured maximum")
    return config


def build_scenario(config: dict[str, Any]) -> dict[str, Any]:
    base = _base_compiler()
    moderate = _moderate_compiler()
    family_config = config["family"]
    family = {
        "id": str(family_config["id"]),
        "layout": "crossing",
        "robot_start": [float(value) for value in config["robot"]["start"]],
        "robot_goal": [float(value) for value in config["robot"]["goal"]],
        "speed_range_mps": [float(value) for value in family_config["speed_range_mps"]],
    }
    split = config["split"]
    scenario = base._build_scenario(
        family,
        density="medium",
        count=int(family_config["pedestrian_count"]),
        split=str(split["name"]),
        seed=int(split["seed"]),
        offset=float(family_config["geometry_offset_m"]),
        map_id=str(config["map"]["id"]),
    )
    moderate._apply_moderation(
        scenario,
        family,
        base,
        config,
        offset=float(family_config["geometry_offset_m"]),
        repeat=int(split["replicate"]),
    )
    metadata = scenario["ramp_metadata"]
    metadata["scenario_id"] = str(config["output"]["scenario_id"])
    metadata["development_scope"] = str(config["status"])
    metadata["source_prior"] = dict(config["source_prior"])
    metadata["held_out_test_materialized"] = False
    bounds = [float(value) for value in config["map"]["bounds_m"]]
    base._validate_scenario(scenario, bounds)
    moderate._validate_actor_routes_against_static_geometry(
        scenario,
        bounds,
        float(config["map"]["preview_resolution_m"]),
        config["moderation"],
    )
    return scenario


def _route_crossing_record(
    actor: dict[str, Any], robot_start_x: float, robot_y: float, robot_speed: float
) -> dict[str, Any]:
    start, end = actor["waypoints"]
    x0, y0 = float(start[0]), float(start[1])
    x1, y1 = float(end[0]), float(end[1])
    if not math.isclose(x0, x1, abs_tol=1.0e-9):
        raise ValueError("crossing anchor actors must follow vertical routes")
    if not min(y0, y1) <= robot_y <= max(y0, y1):
        raise ValueError("actor route does not cross the robot path")
    speed = float(actor["max_vel"])
    actor_eta = abs(robot_y - y0) / speed
    robot_eta = abs(x0 - robot_start_x) / robot_speed
    return {
        "actor": str(actor["name"]),
        "intersection_xy": [x0, robot_y],
        "actor_speed_mps": speed,
        "actor_eta_s": actor_eta,
        "robot_nominal_eta_s": robot_eta,
        "absolute_eta_gap_s": abs(actor_eta - robot_eta),
        "release_clearance_m": abs(float(end[1]) - robot_y),
    }


def audit_scenario(
    scenario: dict[str, Any], config: dict[str, Any], moderate: ModuleType
) -> dict[str, Any]:
    bounds = [float(value) for value in config["map"]["bounds_m"]]
    resolution = float(config["map"]["preview_resolution_m"])
    footprint = float(config["robot"]["radius_m"]) + float(
        config["robot"]["static_path_margin_m"]
    )
    grid, path_cells = moderate._footprint_path(scenario, bounds, resolution, footprint)
    robot = scenario["robots"][0]
    robot_start_x = float(robot["start"][0])
    robot_y = float(robot["start"][1])
    robot_speed = float(config["robot"]["nominal_screen_speed_mps"])
    route_records = [
        _route_crossing_record(actor, robot_start_x, robot_y, robot_speed)
        for actor in scenario["obstacles"]["dynamic"]
    ]
    conflict_window = float(config["screening"]["temporal_conflict_window_s"])
    temporal_conflict_count = sum(
        record["absolute_eta_gap_s"] <= conflict_window for record in route_records
    )
    minimum_release = min(record["release_clearance_m"] for record in route_records)
    robot_goal_x = float(robot["goal"][0])
    robot_goal_y = float(robot["goal"][1])
    start_goal_distance = math.hypot(
        robot_goal_x - robot_start_x, robot_goal_y - robot_y
    )
    last_intersection_x = max(record["intersection_xy"][0] for record in route_records)
    post_conflict_distance = robot_goal_x - last_intersection_x

    first_intersection_x = min(record["intersection_xy"][0] for record in route_records)
    representative_pose = Pose2D(first_intersection_x - 1.0, robot_y, 0.0)
    static_subgoal_count = 0
    for action in ACTIONS:
        if action.kind is not RecoveryActionKind.SUBGOAL:
            continue
        target = action.target_pose(representative_pose)
        assert target is not None
        target_cell = grid.world_to_grid(target.x, target.y)
        if grid.is_free(target_cell) and grid.segment_is_free(
            (representative_pose.x, representative_pose.y), (target.x, target.y)
        ):
            static_subgoal_count += 1

    actors = scenario["obstacles"]["dynamic"]
    one_shot = all(
        actor.get("cyclic_goals") is False and actor.get("behavior", {}).get("once") is True
        for actor in actors
    )
    checks = {
        "development_split_allowed": scenario["ramp_metadata"].get("split")
        in {"train", "validation"},
        "held_out_test_not_materialized": scenario["ramp_metadata"].get(
            "held_out_test_materialized"
        )
        is False,
        "static_path_exists": bool(path_cells),
        "one_shot_release_routes": one_shot,
        "temporal_conflict_present": temporal_conflict_count >= 1,
        "release_clearance_sufficient": minimum_release
        >= float(config["screening"]["minimum_release_clearance_m"]),
        "static_subgoal_space_sufficient": static_subgoal_count
        >= int(config["screening"]["minimum_static_subgoal_count"]),
    }
    maximum_distance = config["screening"].get("maximum_start_goal_distance_m")
    if maximum_distance is not None:
        checks["start_goal_distance_within_limit"] = start_goal_distance <= float(
            maximum_distance
        ) + 1.0e-9
    minimum_post_conflict = config["screening"].get(
        "minimum_post_conflict_distance_m"
    )
    if minimum_post_conflict is not None:
        checks["post_conflict_rejoin_segment_sufficient"] = (
            post_conflict_distance >= float(minimum_post_conflict) - 1.0e-9
        )
    return {
        "schema_version": 1,
        "benchmark_id": config["benchmark_id"],
        "scenario_id": scenario["ramp_metadata"]["scenario_id"],
        "split": scenario["ramp_metadata"]["split"],
        "seed": scenario["ramp_metadata"]["seed"],
        "ready_for_single_seed_runtime_pair": all(checks.values()),
        "checks": checks,
        "route_records": route_records,
        "temporal_conflict_window_s": conflict_window,
        "temporal_conflict_count": temporal_conflict_count,
        "minimum_release_clearance_m": minimum_release,
        "start_goal_distance_m": start_goal_distance,
        "post_conflict_distance_m": post_conflict_distance,
        "static_path_cell_count": len(path_cells),
        "representative_recovery_pose": {
            "x": representative_pose.x,
            "y": representative_pose.y,
            "yaw": representative_pose.yaw,
        },
        "static_subgoal_count": static_subgoal_count,
        "held_out_test_materialized": False,
        "interpretation": (
            "offline geometry/semantics gate only; not a simulator result or paper claim"
        ),
    }


def compile_anchor(config_path: Path, output_root: Path) -> dict[str, Any]:
    config = load_config(config_path)
    scenario = build_scenario(config)
    moderate = _moderate_compiler()
    scenario_id = str(scenario["ramp_metadata"]["scenario_id"])
    map_id = str(config["map"]["id"])
    scenario_path = output_root / "generated" / "arena" / map_id / f"{scenario_id}.json"
    serialized = json.dumps(scenario, indent=2, sort_keys=True) + "\n"
    scenario_path.parent.mkdir(parents=True, exist_ok=True)
    scenario_path.write_text(serialized, encoding="utf-8")
    # Hash the bytes that were actually materialized.  On Windows, text mode
    # may translate LF to CRLF, while WSL/Arena verifies the on-disk bytes.
    scenario_sha256 = hashlib.sha256(scenario_path.read_bytes()).hexdigest()

    bounds = [float(value) for value in config["map"]["bounds_m"]]
    resolution = float(config["map"]["preview_resolution_m"])
    footprint = float(config["robot"]["radius_m"]) + float(
        config["robot"]["static_path_margin_m"]
    )
    grid, path_cells = moderate._footprint_path(scenario, bounds, resolution, footprint)
    preview_path = output_root / "previews" / f"{scenario_id}.png"
    moderate._render_preview(scenario, grid, path_cells, bounds, preview_path)

    report = audit_scenario(scenario, config, moderate)
    report.update(
        {
            "scenario_path": str(scenario_path.resolve()),
            "scenario_sha256": scenario_sha256,
            "preview_path": str(preview_path.resolve()),
            "source_config": str(config_path.resolve()),
        }
    )
    report_path = output_root / "offline_preflight.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = compile_anchor(args.config, args.output_root)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ready_for_single_seed_runtime_pair"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
