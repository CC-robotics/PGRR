#!/usr/bin/env python3
"""Compile one non-test multi-pedestrian closing-gap geometry smoke."""

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

STUDENT_SCRIPTS = Path(__file__).resolve().parent
if str(STUDENT_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(STUDENT_SCRIPTS))

from eight_family_common import base_compiler, load_draft  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "experiments" / "pgrr_extension_v1_eight_family_draft.yaml"
DEFAULT_OUTPUT = ROOT / "outputs" / "student" / "eight_family_geometry_draft"
FAMILY_ID = "closing_gap_multi_pedestrian"


def _module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base() -> ModuleType:
    return base_compiler()


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def _actor(
    index: int, start: list[float], goal: list[float], speed: float, base: ModuleType
) -> dict[str, Any]:
    yaw = math.atan2(goal[1] - start[1], goal[0] - start[0])
    start[2] = yaw
    goal[2] = yaw
    return {
        "name": f"ped_{index:02d}",
        "id": index + 1,
        "pos": start,
        "type": "adult",
        "model": "gazebo_actor",
        "waypoints": [start, goal],
        "max_vel": speed,
        "radius": 0.35,
        "robot_avoidance_distance_m": 0.8,
        "cyclic_goals": False,
        "goal_radius": 0.3,
        "behavior": base._behavior(),
    }


def build(config: dict[str, Any]) -> dict[str, Any]:
    """Build two actors converging from opposite sides of a traversable corridor."""
    if config.get("status") != "draft_train_validation_only_not_executable":
        raise ValueError("only the non-executable eight-family draft is accepted")
    family = next(item for item in config["families"] if item["id"] == FAMILY_ID)
    prototype = family["prototype"]
    geometry = config["prototype_geometry"]
    base = _base()
    seed = int(config["splits"]["train"]["seed_base"]) + 100 * int(family["family_index"]) + 10
    x0, x1 = (float(value) for value in geometry["corridor_x_range_m"])
    south = float(geometry["corridor_south_y_m"])
    north = float(geometry["corridor_north_y_m"])
    static = base._shelves_line((x0, south), (x1, south), prefix="south")
    static += base._shelves_line((x0, north), (x1, north), prefix="north")
    center_y = (south + north) / 2
    half_initial_gap = float(prototype["initial_gap_width_m"]) / 2
    half_closed_gap = float(prototype["closed_gap_width_m"]) / 2
    actors = [
        _actor(
            0,
            [float(prototype["closure_x_m"][0]), center_y - half_initial_gap, 0.0],
            [float(prototype["closure_x_m"][0]), center_y - half_closed_gap, 0.0],
            float(prototype["closing_speed_mps"][0]),
            base,
        ),
        _actor(
            1,
            [float(prototype["closure_x_m"][1]), center_y + half_initial_gap, 0.0],
            [float(prototype["closure_x_m"][1]), center_y + half_closed_gap, 0.0],
            float(prototype["closing_speed_mps"][1]),
            base,
        ),
    ]
    scenario_id = f"{FAMILY_ID}_medium_train_r00_s{seed:05d}"
    payload = {
        "ramp_metadata": {
            "schema_version": 1,
            "benchmark_id": config["benchmark_id"],
            "scenario_id": scenario_id,
            "family": FAMILY_ID,
            "density": "medium",
            "split": "train",
            "seed": seed,
            "replicate": 0,
            "map_id": config["map"]["id"],
            "prototype_status": geometry["status"],
            "assigned_variables": {
                "initial_gap_width_m": prototype["initial_gap_width_m"],
                "closed_gap_width_m": prototype["closed_gap_width_m"],
                "actor_routes": prototype["actor_routes"],
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
    (output_root / "closing_gap_smoke_manifest.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(compile_smoke(args.config.resolve(), args.output_root.resolve()), indent=2))


if __name__ == "__main__":
    main()
