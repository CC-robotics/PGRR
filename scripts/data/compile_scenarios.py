#!/usr/bin/env python3
"""Compile deterministic social-navigation scenarios for the installed Arena schema."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import yaml

matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.patches import Rectangle
from ramp_core.occupancy import OccupancyGrid
from ramp_core.planning.astar import astar

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "experiments" / "scenario_catalog.yaml"


def _shelves_line(
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    prefix: str,
    gap: tuple[float, float] | None = None,
) -> list[dict[str, Any]]:
    """Place 0.9 m Arena shelf models along a line, optionally leaving a gap."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    yaw = math.atan2(dy, dx)
    count = max(1, int(length / 0.82) + 1)
    obstacles: list[dict[str, Any]] = []
    for index in range(count):
        fraction = index / max(1, count - 1)
        x = start[0] + fraction * dx
        y = start[1] + fraction * dy
        coordinate = x if abs(dx) >= abs(dy) else y
        if gap is not None and gap[0] <= coordinate <= gap[1]:
            continue
        obstacles.append({"name": f"{prefix}_{index:02d}", "model": "shelf", "pos": [x, y, yaw]})
    return obstacles


def _static_layout(layout: str, offset: float) -> list[dict[str, Any]]:
    if layout in {"horizontal_corridor", "opposite_streams"}:
        return _shelves_line((4.0, 10.55), (27.0, 10.55), prefix="south") + _shelves_line(
            (4.0, 13.45), (27.0, 13.45), prefix="north"
        )
    if layout in {"doorway", "temporary_blockage"}:
        center = 12.0 + offset
        return _shelves_line(
            (15.5, 3.0),
            (15.5, 21.0),
            prefix="doorwall",
            gap=(center - 0.95, center + 0.95),
        )
    if layout == "blind_corner":
        return _shelves_line((13.0, 3.5), (13.0, 13.3), prefix="corner_v") + _shelves_line(
            (13.0, 13.3), (25.5, 13.3), prefix="corner_h"
        )
    return []


def _human_routes(layout: str, count: int, offset: float) -> list[tuple[list[float], list[float]]]:
    lateral = (-0.55, 0.55, -0.25, 0.25, -0.80, 0.80)
    routes: list[tuple[list[float], list[float]]] = []
    for index in range(count):
        lane = lateral[index % len(lateral)] + offset
        if layout == "horizontal_corridor":
            routes.append(
                ([25.0 - 0.35 * index, 12.0 + lane, math.pi], [5.8, 12.0 + lane, math.pi])
            )
        elif layout == "doorway":
            start_x = 18.5 + 0.45 * (index % 2)
            routes.append(
                ([start_x, 12.0 + lane * 0.5, math.pi], [12.5, 12.0 - lane * 0.3, math.pi])
            )
        elif layout == "crossing":
            x = 12.5 + 1.6 * (index % 4) + offset
            if index % 2:
                routes.append(([x, 6.0, math.pi / 2], [x, 18.0, math.pi / 2]))
            else:
                routes.append(([x, 18.0, -math.pi / 2], [x, 6.0, -math.pi / 2]))
        elif layout == "blind_corner":
            y = 14.6 + 0.45 * (index % 3) + offset
            routes.append(
                ([23.5 - 0.4 * index, y, math.pi], [13.8, 12.2 - 0.35 * index, -math.pi / 2])
            )
        elif layout == "group_blocking":
            x = 15.2 + 0.55 * (index % 3) + offset
            y = 11.45 + 0.55 * (index // 3) + lane * 0.2
            routes.append(([x, y, 0.0], [x + 0.25, y + (-0.2 if index % 2 else 0.2), 0.0]))
        elif layout == "overtaking":
            x = 9.5 + 1.35 * index
            routes.append(([x, 12.0 + lane * 0.45, 0.0], [27.0, 12.0 + lane * 0.45, 0.0]))
        elif layout == "opposite_streams":
            if index % 2:
                routes.append(([5.8, 12.0 + lane, 0.0], [25.5, 12.0 + lane, 0.0]))
            else:
                routes.append(([25.5, 12.0 + lane, math.pi], [5.8, 12.0 + lane, math.pi]))
        elif layout == "temporary_blockage":
            x = 15.5 + 0.22 * lane
            if index % 2:
                routes.append(([x, 10.8 - 0.35 * index, math.pi / 2], [x, 13.2, math.pi / 2]))
            else:
                routes.append(([x, 13.2 + 0.25 * index, -math.pi / 2], [x, 10.8, -math.pi / 2]))
        else:
            raise ValueError(f"unknown scenario layout: {layout}")
    return routes


def _behavior() -> dict[str, Any]:
    return {
        "type": 1,
        "configuration": 0,
        "duration": 60.0,
        "once": False,
        "vel": 0.6,
        "dist": 2.0,
        "goal_force_factor": 2.0,
        "obstacle_force_factor": 40.0,
        "social_force_factor": 5.0,
        "other_force_factor": 10.0,
    }


def _build_scenario(
    family: dict[str, Any],
    *,
    density: str,
    count: int,
    split: str,
    seed: int,
    offset: float,
    map_id: str,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    routes = _human_routes(str(family["layout"]), count, offset)
    speed_min, speed_max = (float(v) for v in family["speed_range_mps"])
    humans: list[dict[str, Any]] = []
    for index, (start, goal) in enumerate(routes):
        speed = float(rng.uniform(speed_min, speed_max))
        humans.append(
            {
                "name": f"ped_{index:02d}",
                "id": index + 1,
                "pos": start,
                "type": "adult",
                "model": "gazebo_actor",
                "waypoints": [start, goal],
                "max_vel": round(speed, 4),
                "radius": 0.35,
                "cyclic_goals": True,
                "goal_radius": 0.3,
                "behavior": _behavior(),
            }
        )
    scenario_id = f"{family['id']}_{density}_{split}_s{seed:05d}"
    return {
        "ramp_metadata": {
            "schema_version": 1,
            "scenario_id": scenario_id,
            "family": family["id"],
            "density": density,
            "split": split,
            "seed": seed,
            "map_id": map_id,
            "human_speed_range_mps": [speed_min, speed_max],
            "human_behavior_model": "HuNav regular social-force",
        },
        "robots": [{"start": family["robot_start"], "goal": family["robot_goal"]}],
        "obstacles": {
            "static": _static_layout(str(family["layout"]), offset),
            "interactive": [],
            "dynamic": humans,
        },
    }


def _validate_scenario(scenario: dict[str, Any], bounds: list[float]) -> None:
    robots = scenario.get("robots")
    obstacles = scenario.get("obstacles")
    if not isinstance(robots, list) or len(robots) != 1:
        raise ValueError("each scenario must contain exactly one robot")
    if not isinstance(obstacles, dict):
        raise ValueError("scenario obstacles must be a mapping")
    dynamic = obstacles.get("dynamic")
    if not isinstance(dynamic, list) or not dynamic:
        raise ValueError("each stress scenario must contain dynamic pedestrians")
    x_min, x_max, y_min, y_max = bounds
    poses: list[list[float]] = [robots[0]["start"], robots[0]["goal"]]
    for human in dynamic:
        if not human.get("waypoints"):
            raise ValueError("every pedestrian requires waypoints")
        poses.extend(human["waypoints"])
    for pose in poses:
        if len(pose) < 2 or not (x_min < float(pose[0]) < x_max and y_min < float(pose[1]) < y_max):
            raise ValueError(f"pose outside map bounds: {pose}")
    names = [str(item["name"]) for item in obstacles.get("static", []) + dynamic]
    if len(names) != len(set(names)):
        raise ValueError("obstacle names must be unique")


def _occupancy(scenario: dict[str, Any], bounds: list[float], resolution: float) -> OccupancyGrid:
    x_min, x_max, y_min, y_max = bounds
    width = math.ceil((x_max - x_min) / resolution)
    height = math.ceil((y_max - y_min) / resolution)
    occupied = np.zeros((height, width), dtype=np.bool_)
    border = math.ceil(0.30 / resolution)
    occupied[:border, :] = True
    occupied[-border:, :] = True
    occupied[:, :border] = True
    occupied[:, -border:] = True
    for item in scenario["obstacles"]["static"]:
        x, y, yaw = (float(value) for value in item["pos"])
        half_x = 0.70 if abs(math.cos(yaw)) >= abs(math.sin(yaw)) else 0.45
        half_y = 0.45 if abs(math.cos(yaw)) >= abs(math.sin(yaw)) else 0.70
        c0 = max(0, math.floor((x - half_x - x_min) / resolution))
        c1 = min(width, math.ceil((x + half_x - x_min) / resolution))
        r0 = max(0, math.floor((y - half_y - y_min) / resolution))
        r1 = min(height, math.ceil((y + half_y - y_min) / resolution))
        occupied[r0:r1, c0:c1] = True
    return OccupancyGrid(occupied, resolution, x_min, y_min)


def _render_preview(
    scenario: dict[str, Any], bounds: list[float], resolution: float, path: Path
) -> None:
    grid = _occupancy(scenario, bounds, resolution)
    robot = scenario["robots"][0]
    start = tuple(float(v) for v in robot["start"][:2])
    goal = tuple(float(v) for v in robot["goal"][:2])
    cells = astar(grid, grid.world_to_grid(*start), grid.world_to_grid(*goal))
    if not cells:
        raise ValueError(f"robot has no static path in {scenario['ramp_metadata']['scenario_id']}")
    world_path = np.asarray([grid.grid_to_world(cell) for cell in cells])
    figure, axis = plt.subplots(figsize=(7.2, 5.5), constrained_layout=True)
    x_min, x_max, y_min, y_max = bounds
    axis.set_xlim(x_min, x_max)
    axis.set_ylim(y_min, y_max)
    axis.set_aspect("equal")
    for item in scenario["obstacles"]["static"]:
        x, y, yaw = (float(v) for v in item["pos"])
        width, height = (0.9, 0.4) if abs(math.cos(yaw)) >= abs(math.sin(yaw)) else (0.4, 0.9)
        axis.add_patch(Rectangle((x - width / 2, y - height / 2), width, height, color="0.25"))
    axis.plot(
        world_path[:, 0], world_path[:, 1], color="#1f77b4", linewidth=2.0, label="static A* path"
    )
    axis.scatter(*start, color="#2ca02c", marker="o", s=60, label="robot start", zorder=4)
    axis.scatter(*goal, color="#d62728", marker="*", s=110, label="robot goal", zorder=4)
    for index, human in enumerate(scenario["obstacles"]["dynamic"]):
        first, last = human["waypoints"][0], human["waypoints"][-1]
        axis.scatter(first[0], first[1], color="#ff7f0e", s=30, zorder=4)
        axis.annotate(
            "",
            xy=(last[0], last[1]),
            xytext=(first[0], first[1]),
            arrowprops={"arrowstyle": "->", "color": "#ff7f0e", "alpha": 0.75},
        )
        axis.text(first[0] + 0.12, first[1] + 0.12, str(index), fontsize=7)
    metadata = scenario["ramp_metadata"]
    axis.set_title(f"{metadata['family']} / {metadata['density']} / {metadata['split']}")
    axis.set_xlabel("x [m]")
    axis.set_ylabel("y [m]")
    axis.legend(loc="upper right", fontsize=7)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160)
    plt.close(figure)


def compile_catalog(config_path: Path, output_root: Path, seed: int) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    bounds = [float(value) for value in config["map"]["bounds_m"]]
    resolution = float(config["map"]["preview_resolution_m"])
    map_id = str(config["map"]["id"])
    manifests: dict[str, list[dict[str, Any]]] = {name: [] for name in config["splits"]}
    seen: set[str] = set()
    for family_index, family in enumerate(config["families"]):
        for density_index, (density, count) in enumerate(config["densities"].items()):
            for split, split_config in config["splits"].items():
                scenario_seed = (
                    seed
                    + int(split_config["seed_offset"])
                    + family_index * 100
                    + density_index * 10
                )
                scenario = _build_scenario(
                    family,
                    density=density,
                    count=int(count),
                    split=split,
                    seed=scenario_seed,
                    offset=float(split_config["geometry_offset_m"]),
                    map_id=map_id,
                )
                _validate_scenario(scenario, bounds)
                scenario_id = str(scenario["ramp_metadata"]["scenario_id"])
                if scenario_id in seen:
                    raise ValueError(f"duplicate scenario id: {scenario_id}")
                seen.add(scenario_id)
                relative = Path("arena") / map_id / f"{scenario_id}.json"
                destination = output_root / "generated" / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                text = json.dumps(scenario, indent=2, sort_keys=True) + "\n"
                destination.write_text(text, encoding="utf-8")
                digest = hashlib.sha256(text.encode()).hexdigest()
                preview = output_root / "previews" / f"{scenario_id}.png"
                _render_preview(scenario, bounds, resolution, preview)
                manifests[split].append(
                    {
                        "scenario_id": scenario_id,
                        "family": family["id"],
                        "density": density,
                        "map_id": map_id,
                        "seed": scenario_seed,
                        "path": str(relative),
                        "sha256": digest,
                    }
                )
    manifest_dir = output_root / "splits"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    for split, records in manifests.items():
        payload = {"schema_version": 1, "split": split, "scenarios": records}
        (manifest_dir / f"{split}.yaml").write_text(
            yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
        )
    summary = {
        "schema_version": 1,
        "source_config": str(config_path.relative_to(ROOT)),
        "base_seed": seed,
        "scenario_count": len(seen),
        "counts_by_split": {name: len(records) for name, records in manifests.items()},
        "scenario_ids_sha256": hashlib.sha256("\n".join(sorted(seen)).encode()).hexdigest(),
    }
    summary_dir = output_root / "manifests"
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / "scenario_catalog.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=ROOT / "scenarios")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    summary = compile_catalog(args.config.resolve(), args.output_root.resolve(), args.seed)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
