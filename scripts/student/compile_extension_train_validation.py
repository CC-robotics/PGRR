#!/usr/bin/env python3
"""Compile smoke-only PGRR extension train/validation scenarios and previews.

The compiler is intentionally isolated under ``scripts/student``.  It uses
preliminary geometry to check schema, static reachability, and preview
rendering only.  It never writes to scenarios/generated, does not materialize
a test split, and does not start Arena/ROS.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "experiments" / "pgrr_extension_v1_train_validation.yaml"
DEFAULT_OUTPUT = ROOT / "outputs" / "student" / "extension_scenario_smoke"


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load helper module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base_compiler() -> ModuleType:
    return _load_module(
        "pgrr_base_scenario_compiler",
        ROOT / "scripts" / "data" / "compile_scenarios.py",
    )


def _split_plan() -> ModuleType:
    return _load_module(
        "pgrr_extension_split_plan",
        ROOT / "scripts" / "student" / "validate_extension_split.py",
    )


def _yaw(start: Sequence[float], goal: Sequence[float]) -> float:
    return math.atan2(float(goal[1]) - float(start[1]), float(goal[0]) - float(start[0]))


def _actor(
    name: str,
    start: list[float],
    goal: list[float],
    speed: float,
    base: ModuleType,
) -> dict[str, Any]:
    start[2] = _yaw(start, goal)
    goal[2] = start[2]
    behavior = base._behavior()
    behavior["once"] = True
    return {
        "name": name,
        "id": int(name.rsplit("_", maxsplit=1)[-1]) + 1,
        "pos": start,
        "type": "adult",
        "model": "gazebo_actor",
        "waypoints": [start, goal],
        "max_vel": round(speed, 4),
        "radius": 0.35,
        "robot_avoidance_distance_m": 0.8,
        "cyclic_goals": False,
        "goal_radius": 0.3,
        "behavior": behavior,
    }


def _corridor_static(geometry: dict[str, Any], base: ModuleType) -> list[dict[str, Any]]:
    x0, x1 = (float(value) for value in geometry["corridor_x_range_m"])
    return base._shelves_line(
        (x0, float(geometry["corridor_south_y_m"])),
        (x1, float(geometry["corridor_south_y_m"])),
        prefix="south",
    ) + base._shelves_line(
        (x0, float(geometry["corridor_north_y_m"])),
        (x1, float(geometry["corridor_north_y_m"])),
        prefix="north",
    )


def _choose(values: list[Any], seed: int, salt: int) -> Any:
    return values[(seed + salt) % len(values)]


def _diagonal_cut_in(
    condition: dict[str, Any], family: dict[str, Any], geometry: dict[str, Any], base: ModuleType
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    seed = int(condition["seed"])
    variables = family["variables"]
    prototype = family["prototype"]
    side = str(_choose(variables["cut_side"], seed, 0))
    cut_x = float(_choose(prototype["cut_x_m"], seed, 1))
    span = float(prototype["crossing_span_m"])
    lower = float(geometry["corridor_south_y_m"]) + 0.45
    upper = float(geometry["corridor_north_y_m"]) - 0.45
    start_y, goal_y = (lower, upper) if side == "left" else (upper, lower)
    speed_ratio = float(_choose(variables["speed_ratio_to_robot_nominal"], seed, 2))
    speed = 0.60 * speed_ratio
    actors = [
        _actor(
            "ped_00",
            [cut_x - span / 2, start_y, 0.0],
            [cut_x + span / 2, goal_y, 0.0],
            speed,
            base,
        )
    ]
    for index in range(1, int(condition["pedestrian_count"])):
        x = cut_x + 1.3 * index
        actors.append(
            _actor(
                f"ped_{index:02d}",
                [x - span / 2, start_y, 0.0],
                [x + span / 2, goal_y, 0.0],
                speed,
                base,
            )
        )
    assigned = {
        "cut_side": side,
        "cut_angle_deg": _choose(variables["cut_angle_deg"], seed, 3),
        "longitudinal_phase": _choose(variables["longitudinal_phase"], seed, 4),
        "speed_ratio_to_robot_nominal": speed_ratio,
        "lateral_offset_m": _choose(variables["lateral_offset_m"], seed, 5),
    }
    return _corridor_static(geometry, base), actors, assigned


def _occluded_side_emergence(
    condition: dict[str, Any], family: dict[str, Any], geometry: dict[str, Any], base: ModuleType
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    seed = int(condition["seed"])
    variables = family["variables"]
    prototype = family["prototype"]
    static = _corridor_static(geometry, base)
    screen_x = float(_choose(prototype["screen_x_m"], seed, 0))
    screen_y = float(prototype["screen_center_y_m"])
    length = float(prototype["screen_length_m"])
    static += base._shelves_line(
        (screen_x, screen_y - length / 2),
        (screen_x, screen_y + length / 2),
        prefix="occluder",
    )
    side = str(_choose(variables["emergence_side"], seed, 1))
    lower = float(geometry["corridor_south_y_m"]) + 0.48
    upper = float(geometry["corridor_north_y_m"]) - 0.48
    start_y, goal_y = (lower, upper) if side == "left" else (upper, lower)
    speed = float(_choose(variables["pedestrian_speed_mps"], seed, 2))
    actors = [
        _actor(
            "ped_00",
            [screen_x, start_y, 0.0],
            [screen_x + 0.8, goal_y, 0.0],
            speed,
            base,
        )
    ]
    for index in range(1, int(condition["pedestrian_count"])):
        x = screen_x + 1.1 * index
        actors.append(
            _actor(
                f"ped_{index:02d}",
                [x, start_y, 0.0],
                [x + 0.8, goal_y, 0.0],
                speed,
                base,
            )
        )
    assigned = {
        "emergence_side": side,
        "first_visible_distance_m": _choose(variables["first_visible_distance_m"], seed, 3),
        "gap_location": _choose(variables["gap_location"], seed, 4),
        "longitudinal_phase": _choose(variables["longitudinal_phase"], seed, 5),
        "pedestrian_speed_mps": speed,
    }
    return static, actors, assigned


def build_scenario(condition: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Build one preliminary, one-shot Arena schema payload for a planned condition."""
    base = _base_compiler()
    geometry = dict(config["prototype_geometry"])
    family = next(item for item in config["families"] if item["id"] == condition["family"])
    builders = {
        "diagonal_cut_in_corridor": _diagonal_cut_in,
        "occluded_side_emergence": _occluded_side_emergence,
    }
    static, actors, assigned = builders[str(condition["family"])](condition, family, geometry, base)
    scenario_id = f"{condition['condition_id']}_s{int(condition['seed']):05d}"
    payload = {
        "ramp_metadata": {
            "schema_version": 1,
            "benchmark_id": config["benchmark_id"],
            "scenario_id": scenario_id,
            "family": condition["family"],
            "density": condition["density"],
            "split": condition["split"],
            "seed": condition["seed"],
            "replicate": condition["repeat_index"],
            "map_id": config["map"]["id"],
            "prototype_status": geometry["status"],
            "assigned_variables": assigned,
        },
        "robots": [{"start": geometry["robot_start"], "goal": geometry["robot_goal"]}],
        "obstacles": {"static": static, "interactive": [], "dynamic": actors},
    }
    base._validate_scenario(payload, [float(value) for value in config["map"]["bounds_m"]])
    return payload


def compile_smoke(
    config_path: Path,
    output_root: Path,
    limit: int,
    family_id: str | None = None,
    split: str | None = None,
) -> dict[str, Any]:
    """Compile up to ``limit`` planned train/validation conditions and previews."""
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("status") != "planning_train_validation_only":
        raise ValueError("extension catalog must remain train/validation planning only")
    conditions = _split_plan().planned_conditions(config)
    if family_id is not None:
        conditions = [item for item in conditions if item["family"] == family_id]
        if not conditions:
            raise ValueError(f"unknown extension family: {family_id}")
    if split is not None:
        if split not in {"train", "validation"}:
            raise ValueError("split must be train or validation")
        conditions = [item for item in conditions if item["split"] == split]
    if limit < 1 or limit > len(conditions):
        raise ValueError(f"limit must be in [1, {len(conditions)}]")
    base = _base_compiler()
    bounds = [float(value) for value in config["map"]["bounds_m"]]
    resolution = float(config["map"]["preview_resolution_m"])
    map_id = str(config["map"]["id"])
    records: list[dict[str, Any]] = []
    for condition in conditions[:limit]:
        payload = build_scenario(condition, config)
        scenario_id = payload["ramp_metadata"]["scenario_id"]
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        relative_path = Path("generated") / "arena" / map_id / f"{scenario_id}.json"
        destination = output_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
        preview_path = output_root / "previews" / f"{scenario_id}.png"
        base._render_preview(payload, bounds, resolution, preview_path)
        records.append(
            {
                "condition_id": condition["condition_id"],
                "scenario_id": scenario_id,
                "split": condition["split"],
                "seed": condition["seed"],
                "path": str(relative_path).replace("\\", "/"),
                "preview": str(preview_path.relative_to(output_root)).replace("\\", "/"),
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
        )
    if any(record["split"] not in {"train", "validation"} for record in records):
        raise AssertionError("smoke compiler must never materialize test conditions")
    report = {
        "benchmark_id": config["benchmark_id"],
        "status": "smoke_only",
        "compiled_count": len(records),
        "held_out_test_materialized": False,
        "records": records,
    }
    labels = [family_id if family_id is not None else "all_families"]
    if split is not None:
        labels.append(split)
    label = "_".join(labels)
    report_path = output_root / f"smoke_manifest_{label}_{limit:02d}.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--limit",
        type=int,
        default=2,
        help="number of train/validation smoke cases",
    )
    parser.add_argument("--family", help="optional approved family to compile")
    parser.add_argument(
        "--split",
        choices=("train", "validation"),
        help="optionally compile only one non-test split",
    )
    args = parser.parse_args(argv)
    report = compile_smoke(
        args.config.resolve(),
        args.output_root.resolve(),
        args.limit,
        family_id=args.family,
        split=args.split,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
