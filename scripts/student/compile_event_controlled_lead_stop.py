#!/usr/bin/env python3
"""Compile one train-only bounded lead-stop event scenario."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml
from ramp_core.scenario import ScenarioEventController, event_spec_from_contract

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT = (
    ROOT / "configs/experiments/pgrr_event_controlled_anchor_contract_v1.yaml"
)
DEFAULT_DRAFT = ROOT / "configs/experiments/pgrr_extension_v1_eight_family_draft.yaml"
DEFAULT_OUTPUT = ROOT / "outputs/student/event_controlled_candidates"
FAMILY = "lead_pedestrian_sudden_stop"
ACTOR_NAME = "ped_00"


def _display_path(path: Path) -> str:
    """Return a stable repo-relative path, or an absolute test-temp path."""

    try:
        shown = path.relative_to(ROOT)
    except ValueError:
        shown = path
    return str(shown).replace("\\", "/")


def _module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base() -> ModuleType:
    return _module(
        "event_lead_stop_base", ROOT / "scripts/data/compile_scenarios.py"
    )


def _distance_to_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    goal: tuple[float, float],
) -> float:
    dx, dy = goal[0] - start[0], goal[1] - start[1]
    denominator = dx * dx + dy * dy
    if denominator <= 1.0e-12:
        return math.dist(point, start)
    fraction = max(
        0.0,
        min(
            1.0,
            ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy)
            / denominator,
        ),
    )
    projection = start[0] + fraction * dx, start[1] + fraction * dy
    return math.dist(point, projection)


def compile_candidate(
    contract_path: Path,
    draft_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Materialize exactly one train scenario; never create validation or test."""

    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    draft = yaml.safe_load(draft_path.read_text(encoding="utf-8"))
    if contract.get("status") != "draft_train_validation_only_non_executable":
        raise ValueError("unexpected event contract status")
    if draft.get("status") != "draft_train_validation_only_not_executable":
        raise ValueError("unexpected geometry draft status")
    variant = next(item for item in contract["variants"] if item["family"] == FAMILY)
    spec = event_spec_from_contract(variant, split="train")
    geometry = draft["prototype_geometry"]
    bounds = [float(value) for value in draft["map"]["bounds_m"]]
    base = _base()
    south_y = float(geometry["corridor_south_y_m"])
    north_y = float(geometry["corridor_north_y_m"])
    x0, x1 = (float(value) for value in geometry["corridor_x_range_m"])
    static = base._shelves_line((x0, south_y), (x1, south_y), prefix="south")
    # Leave a deliberate exit opening near the far end. The actor exits only
    # after passing the robot goal, so the release cannot become a terminal block.
    static.extend(
        obstacle
        for obstacle in base._shelves_line(
            (x0, north_y), (x1, north_y), prefix="north"
        )
        if float(obstacle["pos"][0]) < 25.0
    )
    center_y = (south_y + north_y) / 2.0
    robot_start = tuple(float(value) for value in geometry["robot_start"][:2])
    robot_goal = tuple(float(value) for value in geometry["robot_goal"][:2])
    actor_waypoints = [
        # v2 keeps the far-side arming margin but moves the challenge earlier
        # in the episode. v1 started at x=10.0 with 0.20 m/s and did not
        # activate until simulation time 80.02 s.
        [8.75, center_y, 0.0],
        [23.0, center_y, 0.0],
        [29.0, north_y + 1.35, 0.0],
    ]
    actor_speed_mps = 0.10
    terminal_clearance = _distance_to_segment(
        tuple(actor_waypoints[-1][:2]), robot_start, robot_goal
    )
    if terminal_clearance < 1.0:
        raise ValueError("released actor terminal waypoint does not clear robot route")
    event_mapping = {
        "schema_version": 1,
        "events": [
            {
                "event_id": "lead_stop_bounded_release_v2_train",
                "actor_name": ACTOR_NAME,
                "trigger_metric": spec.trigger_metric.value,
                "trigger_threshold_m": spec.trigger_threshold_m,
                "trigger_hysteresis_m": spec.trigger_hysteresis_m,
                "active_duration_s": spec.active_duration_s,
                "commands": {
                    "pre_event": spec.pre_event_command,
                    "active_event": spec.active_event_command,
                    "released": spec.released_command,
                },
            }
        ],
    }
    ScenarioEventController.from_mapping(event_mapping, actor_names={ACTOR_NAME})
    seed = int(variant["train"]["seed"])
    scenario_id = f"lead_stop_bounded_release_v2_train_r00_s{seed}"
    actor = {
        "name": ACTOR_NAME,
        "id": 1,
        "pos": actor_waypoints[0],
        "type": "adult",
        "model": "gazebo_actor",
        "waypoints": actor_waypoints,
        "max_vel": actor_speed_mps,
        "radius": 0.35,
        "robot_avoidance_distance_m": 0.8,
        "cyclic_goals": False,
        "goal_radius": 0.3,
        "behavior": base._behavior(),
    }
    payload = {
        "ramp_metadata": {
            "schema_version": 1,
            "benchmark_id": "pgrr_extension_event_candidates_v1",
            "scenario_id": scenario_id,
            "family": FAMILY,
            "variant_id": variant["variant_id"],
            "density": "low",
            "split": "train",
            "seed": seed,
            "replicate": 0,
            "map_id": draft["map"]["id"],
            "candidate_status": "train_only_pre_runtime_validation",
            "paired_methods": ["base", "pgrr"],
            "event_control_required": True,
            "assigned_variables": {
                "lead_speed_mps": actor_speed_mps,
                "stop_duration_s": spec.active_duration_s,
                "trigger_distance_m": spec.trigger_threshold_m,
                "terminal_route_clearance_m": terminal_clearance,
            },
        },
        "ramp_event_control": event_mapping,
        "robots": [
            {
                "start": [*robot_start, float(geometry["robot_start"][2])],
                "goal": [*robot_goal, float(geometry["robot_goal"][2])],
            }
        ],
        "obstacles": {"static": static, "interactive": [], "dynamic": [actor]},
    }
    base._validate_scenario(payload, bounds)
    destination = (
        output_root
        / "generated/arena"
        / str(draft["map"]["id"])
        / f"{scenario_id}.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    destination.write_text(text, encoding="utf-8")
    preview = output_root / "previews" / f"{scenario_id}.png"
    preview.parent.mkdir(parents=True, exist_ok=True)
    base._render_preview(
        payload,
        bounds,
        float(draft["map"]["preview_resolution_m"]),
        preview,
    )
    report = {
        "candidate_id": scenario_id,
        "family": FAMILY,
        "split": "train",
        "seed": seed,
        "held_out_test_materialized": False,
        "paired_methods_share_one_scenario": True,
        "event_mapping_valid": True,
        "actor_route_noncyclic": actor["cyclic_goals"] is False,
        "actor_terminal_route_clearance_m": terminal_clearance,
        "initial_trigger_metric_m": math.dist(robot_start, tuple(actor_waypoints[0][:2])),
        "trigger_arm_threshold_m": (
            spec.trigger_threshold_m + spec.trigger_hysteresis_m
        ),
        "scenario_path": _display_path(destination),
        "preview_path": _display_path(preview),
        "scenario_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "runtime_executed": False,
    }
    report_path = output_root / "lead_stop_bounded_release_v2_train_manifest.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--draft", type=Path, default=DEFAULT_DRAFT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = compile_candidate(
        args.contract.resolve(), args.draft.resolve(), args.output_root.resolve()
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
