#!/usr/bin/env python3
"""Compile one non-test lead-pedestrian terminal-stop geometry smoke."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "experiments" / "pgrr_extension_v1_eight_family_draft.yaml"
DEFAULT_OUTPUT = ROOT / "outputs" / "student" / "eight_family_geometry_draft"
FAMILY_ID = "lead_pedestrian_sudden_stop"


def _module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base() -> ModuleType:
    return _module(
        "eight_family_common", ROOT / "scripts/student/eight_family_common.py"
    ).base_compiler()


def _load_draft(path: Path) -> dict[str, Any]:
    return _module(
        "eight_family_common", ROOT / "scripts/student/eight_family_common.py"
    ).load_draft(path)


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def compile_smoke(
    config_path: Path, output_root: Path, *, split: str = "train"
) -> dict[str, Any]:
    """Emit one low-density non-test scenario with a terminal-stop lead actor."""
    config = _load_draft(config_path)
    if (
        not isinstance(config, dict)
        or config.get("status") != "draft_train_validation_only_not_executable"
    ):
        raise ValueError("only the non-executable eight-family draft is accepted")
    if split not in {"train", "validation"}:
        raise ValueError("split must be train or validation")
    family = next(item for item in config["families"] if item["id"] == FAMILY_ID)
    geometry = config["prototype_geometry"]
    prototype = family["prototype"]
    base = _base()
    seed = int(config["splits"][split]["seed_base"]) + 100 * int(family["family_index"])
    x0, x1 = (float(value) for value in geometry["corridor_x_range_m"])
    south, north = float(geometry["corridor_south_y_m"]), float(geometry["corridor_north_y_m"])
    static = base._shelves_line((x0, south), (x1, south), prefix="south")
    static += base._shelves_line((x0, north), (x1, north), prefix="north")
    center_y = (south + north) / 2
    start = [float(prototype["lead_start_x_m"]), center_y, 0.0]
    goal = [float(prototype["lead_stop_x_m"]), center_y, 0.0]
    actor = {
        "name": "ped_00",
        "id": 1,
        "pos": start,
        "type": "adult",
        "model": "gazebo_actor",
        "waypoints": [start, goal],
        "max_vel": float(prototype["lead_speed_mps"]),
        "radius": 0.35,
        "robot_avoidance_distance_m": 0.8,
        "cyclic_goals": False,
        "goal_radius": 0.3,
        "behavior": base._behavior(),
    }
    scenario_id = f"{FAMILY_ID}_low_{split}_r00_s{seed:05d}"
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
            "prototype_status": geometry["status"],
            "assigned_variables": {
                "lead_speed_mps": prototype["lead_speed_mps"],
                "actor_routes": prototype["actor_routes"],
            },
        },
        "robots": [{"start": geometry["robot_start"], "goal": geometry["robot_goal"]}],
        "obstacles": {"static": static, "interactive": [], "dynamic": [actor]},
    }
    base._validate_scenario(payload, [float(value) for value in config["map"]["bounds_m"]])
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
        "split": split,
        "held_out_test_materialized": False,
        "json": _display_path(destination),
        "preview": _display_path(preview),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    (output_root / f"lead_stop_{split}_smoke_manifest.json").write_text(
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
