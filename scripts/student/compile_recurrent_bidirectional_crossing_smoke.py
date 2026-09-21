#!/usr/bin/env python3
"""Compile one non-test geometry smoke for recurrent bidirectional crossing.

The result is a preliminary JSON and top-down preview only.  It never starts
Arena/ROS, trains a model, or emits a held-out-test condition.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

STUDENT_SCRIPTS = Path(__file__).resolve().parent
if str(STUDENT_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(STUDENT_SCRIPTS))

from eight_family_common import base_compiler, load_draft  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "experiments" / "pgrr_extension_v1_eight_family_draft.yaml"
DEFAULT_OUTPUT = ROOT / "outputs" / "student" / "eight_family_geometry_draft"
FAMILY_ID = "recurrent_bidirectional_crossing"


def _module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base() -> ModuleType:
    return base_compiler()


def _condition(config: dict[str, Any]) -> dict[str, Any]:
    """Return the fixed medium-density train smoke condition for family #3."""
    family = next(item for item in config["families"] if item["id"] == FAMILY_ID)
    seed = int(config["splits"]["train"]["seed_base"]) + 100 * int(family["family_index"]) + 10
    return {
        "family": FAMILY_ID,
        "family_index": int(family["family_index"]),
        "density": "medium",
        "pedestrian_count": int(config["densities"]["medium"]),
        "split": "train",
        "repeat_index": 0,
        "seed": seed,
        "condition_id": f"{FAMILY_ID}_medium_train_r00",
    }


def _display_path(path: Path) -> str:
    """Prefer a repository-relative path, retaining an absolute temp path in tests."""
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def build(config: dict[str, Any]) -> dict[str, Any]:
    """Build two cyclic actors crossing in opposite directions through a corridor."""
    if config.get("status") != "draft_train_validation_only_not_executable":
        raise ValueError("only the non-executable eight-family draft is accepted")
    geometry = config["prototype_geometry"]
    family = next(item for item in config["families"] if item["id"] == FAMILY_ID)
    condition = _condition(config)
    prototype = family["prototype"]
    base = _base()
    x0, x1 = (float(value) for value in geometry["corridor_x_range_m"])
    static = base._shelves_line(
        (x0, float(geometry["corridor_south_y_m"])),
        (x1, float(geometry["corridor_south_y_m"])),
        prefix="south",
    )
    static += base._shelves_line(
        (x0, float(geometry["corridor_north_y_m"])),
        (x1, float(geometry["corridor_north_y_m"])),
        prefix="north",
    )
    lower = float(geometry["corridor_south_y_m"]) + 0.48
    upper = float(geometry["corridor_north_y_m"]) - 0.48
    span = float(prototype["crossing_span_m"])
    actors: list[dict[str, Any]] = []
    for index, x in enumerate(prototype["crossing_x_m"]):
        start_y, goal_y = (lower, upper) if index % 2 == 0 else (upper, lower)
        start = [float(x) - span / 2, start_y, 0.0]
        goal = [float(x) + span / 2, goal_y, 0.0]
        start[2] = base.math.atan2(goal[1] - start[1], goal[0] - start[0])
        goal[2] = start[2]
        actor = {
            "name": f"ped_{index:02d}",
            "id": index + 1,
            "pos": start,
            "type": "adult",
            "model": "gazebo_actor",
            "waypoints": [start, goal],
            "max_vel": float(prototype["pedestrian_speed_mps"][index]),
            "radius": 0.35,
            "robot_avoidance_distance_m": 1.3,
            "cyclic_goals": True,
            "goal_radius": 0.3,
            "behavior": base._behavior(),
        }
        actors.append(actor)
    scenario_id = f"{condition['condition_id']}_s{condition['seed']:05d}"
    payload = {
        "ramp_metadata": {
            "schema_version": 1,
            "benchmark_id": config["benchmark_id"],
            "scenario_id": scenario_id,
            "family": FAMILY_ID,
            "density": condition["density"],
            "split": "train",
            "seed": condition["seed"],
            "replicate": 0,
            "map_id": config["map"]["id"],
            "prototype_status": geometry["status"],
            "assigned_variables": {
                "crossing_interval_s": prototype["crossing_interval_s"],
                "actor_routes": prototype["actor_routes"],
                "direction_balance": "one_each_direction",
            },
        },
        "robots": [{"start": geometry["robot_start"], "goal": geometry["robot_goal"]}],
        "obstacles": {"static": static, "interactive": [], "dynamic": actors},
    }
    base._validate_scenario(payload, [float(value) for value in config["map"]["bounds_m"]])
    return payload


def compile_smoke(config_path: Path, output_root: Path) -> dict[str, Any]:
    config = load_draft(config_path)
    payload = build(config)
    scenario_id = payload["ramp_metadata"]["scenario_id"]
    destination = (
        output_root / "generated" / "arena" / str(config["map"]["id"]) / f"{scenario_id}.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    destination.write_text(text, encoding="utf-8")
    preview = output_root / "previews" / f"{scenario_id}.png"
    preview.parent.mkdir(parents=True, exist_ok=True)
    _base()._render_preview(
        payload,
        [float(value) for value in config["map"]["bounds_m"]],
        float(config["map"]["preview_resolution_m"]),
        preview,
    )
    report = {
        "status": "geometry_smoke_only",
        "family": FAMILY_ID,
        "scenario_id": scenario_id,
        "split": "train",
        "held_out_test_materialized": False,
        "json": _display_path(destination),
        "preview": _display_path(preview),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    report_path = output_root / "recurrent_bidirectional_crossing_smoke_manifest.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(compile_smoke(args.config.resolve(), args.output_root.resolve()), indent=2))


if __name__ == "__main__":
    main()
