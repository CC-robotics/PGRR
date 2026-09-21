#!/usr/bin/env python3
"""Compile one non-test narrow-corridor head-on geometry smoke."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "experiments" / "pgrr_extension_v1_eight_family_draft.yaml"
DEFAULT_OUTPUT = ROOT / "outputs" / "student" / "eight_family_geometry_draft"
FAMILY_ID = "narrow_corridor_head_on_deadlock"


def _module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base() -> ModuleType:
    common = _module(
        "eight_family_common", ROOT / "scripts/student/eight_family_common.py"
    )
    return common.base_compiler()


def _load_draft(path: Path) -> dict[str, Any]:
    return _module(
        "eight_family_common", ROOT / "scripts/student/eight_family_common.py"
    ).load_draft(path)


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def build(config: dict[str, Any], *, split: str = "train") -> dict[str, Any]:
    """Build a static-reachable corridor with one opposing, one-shot actor."""
    if config.get("status") != "draft_train_validation_only_not_executable":
        raise ValueError("only the non-executable eight-family draft is accepted")
    if split not in {"train", "validation"}:
        raise ValueError("split must be train or validation")
    family = next(item for item in config["families"] if item["id"] == FAMILY_ID)
    prototype = family["prototype"]
    base = _base()
    seed = int(config["splits"][split]["seed_base"]) + 100 * int(family["family_index"])
    center_y = float(prototype["corridor_center_y_m"])
    half_width = float(prototype["corridor_width_m"]) / 2
    x0, x1 = (float(value) for value in prototype["corridor_x_range_m"])
    static = base._shelves_line(
        (x0, center_y - half_width), (x1, center_y - half_width), prefix="south"
    )
    static += base._shelves_line(
        (x0, center_y + half_width), (x1, center_y + half_width), prefix="north"
    )
    start = [float(prototype["oncoming_start_x_m"]), center_y, math.pi]
    goal = [float(prototype["oncoming_goal_x_m"]), center_y, math.pi]
    actor = {
        "name": "ped_00",
        "id": 1,
        "pos": start,
        "type": "adult",
        "model": "gazebo_actor",
        "waypoints": [start, goal],
        "max_vel": float(prototype["oncoming_speed_mps"]),
        "radius": 0.35,
        "robot_avoidance_distance_m": 0.8,
        "cyclic_goals": False,
        "goal_radius": 0.3,
        "behavior": base._behavior(),
    }
    condition_id = f"{FAMILY_ID}_low_{split}_r00"
    scenario_id = f"{condition_id}_s{seed:05d}"
    payload = {
        "ramp_metadata": {
            "schema_version": 1,
            "benchmark_id": config["benchmark_id"],
            "scenario_id": scenario_id,
            "family": FAMILY_ID,
            "density": "low",
            "split": split,
            "seed": seed,
            "replicate": 0,
            "map_id": config["map"]["id"],
            "prototype_status": config["prototype_geometry"]["status"],
            "assigned_variables": {
                "corridor_width_m": prototype["corridor_width_m"],
                "oncoming_speed_mps": prototype["oncoming_speed_mps"],
                "actor_routes": prototype["actor_routes"],
            },
        },
        "robots": [
            {
                "start": config["prototype_geometry"]["robot_start"],
                "goal": config["prototype_geometry"]["robot_goal"],
            }
        ],
        "obstacles": {"static": static, "interactive": [], "dynamic": [actor]},
    }
    base._validate_scenario(payload, [float(value) for value in config["map"]["bounds_m"]])
    return payload


def compile_smoke(
    config_path: Path, output_root: Path, *, split: str = "train"
) -> dict[str, Any]:
    config = _load_draft(config_path)
    payload = build(config, split=split)
    scenario_id = payload["ramp_metadata"]["scenario_id"]
    output_dir = output_root / "generated" / "arena" / str(config["map"]["id"])
    destination = output_dir / f"{scenario_id}.json"
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
        "split": split,
        "held_out_test_materialized": False,
        "json": _display_path(destination),
        "preview": _display_path(preview),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    (output_root / f"narrow_corridor_head_on_{split}_smoke_manifest.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--split", choices=("train", "validation"), default="train")
    args = parser.parse_args()
    print(
        json.dumps(
            compile_smoke(
                args.config.resolve(), args.output_root.resolve(), split=args.split
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
