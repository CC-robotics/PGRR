#!/usr/bin/env python3
"""Compile a moderate, split-safe social-navigation benchmark for Arena.

The benchmark deliberately changes the scenario distribution rather than
post-selecting successful episodes: pedestrian counts are 1/2/4, every route
is one-shot, and all configured splits use disjoint predeclared seed blocks.
Static reachability is checked with A* after inflating shelf footprints by the
robot radius and a configured clearance margin.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
from dataclasses import dataclass
from itertools import combinations, pairwise
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import matplotlib
import numpy as np
import yaml

matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.patches import Rectangle
from ramp_core.occupancy import OccupancyGrid
from ramp_core.planning.astar import astar

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "experiments" / "scenario_catalog_moderate.yaml"
EXPECTED_FAMILIES = (
    "head_on_corridor",
    "doorway_bottleneck",
    "crossing_flow",
    "blind_corner",
    "group_blocking",
    "overtaking",
    "opposite_streams",
    "temporary_blockage",
)
EXPECTED_DENSITIES = {"low": 1, "medium": 2, "high": 4}
SUFFIX_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
COMBINED_COLLISION_RADIUS_M = 0.71
SEED_BLOCK_SIZE = 1_000
EGRESS_EXIT_KEYS = {
    "head_on_corridor": "head_on_exit_x_m",
    "doorway_bottleneck": "doorway_exit_x_m",
}
V5_CALIBRATION_KEYS = {
    "blind_corner_vertical_end_y_m",
    "blind_corner_horizontal_start_x_m",
    "group_nearest_actor_offset_m",
    "overtaking_lane_offset_range_m",
    "opposite_stream_lane_offset_range_m",
    "temporary_doorway_center_half_gap_m",
    "temporary_crossing_half_span_m",
    "temporary_crossing_x_spacing_m",
    "temporary_crossing_lead_in_m",
    "validate_actor_static_clearance",
}


@dataclass(frozen=True)
class CompiledScenario:
    """Validated scenario plus deterministic artifact metadata."""

    split: str
    record: dict[str, Any]
    payload: dict[str, Any]
    serialized: str
    relative_path: Path
    preview_relative_path: Path
    path_cells: tuple[tuple[int, int], ...]


def _load_base_compiler() -> ModuleType:
    """Load the installed-schema compiler without requiring scripts as a package."""

    path = ROOT / "scripts" / "data" / "compile_scenarios.py"
    spec = importlib.util.spec_from_file_location("pgrr_base_scenario_compiler", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load base scenario compiler: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validate_suffix(value: str) -> str:
    suffix = value.strip().lower()
    if not SUFFIX_PATTERN.fullmatch(suffix):
        raise ValueError("manifest suffix must contain only lowercase letters, digits, _ or -")
    return suffix


def _positive_repetitions(value: int, split: str) -> int:
    if not 1 <= value <= 10:
        raise ValueError(f"{split} repetitions must be in [1, 10]")
    return value


def _assert_seed_blocks_disjoint(seed_bases: dict[str, int]) -> None:
    """Reserve one decimal 1,000-seed block for every configured split."""

    for left, right in combinations(seed_bases, 2):
        left_base = seed_bases[left]
        right_base = seed_bases[right]
        overlap = max(left_base, right_base) < min(
            left_base + SEED_BLOCK_SIZE,
            right_base + SEED_BLOCK_SIZE,
        )
        if overlap:
            raise ValueError(f"{left}/{right} seed blocks must differ and not overlap")


def _validate_config(config: dict[str, Any]) -> None:
    if int(config.get("schema_version", -1)) != 1:
        raise ValueError("moderate catalog schema_version must be 1")
    families = config.get("families")
    if not isinstance(families, list):
        raise ValueError("families must be a list")
    family_ids = tuple(str(family.get("id")) for family in families)
    if family_ids != EXPECTED_FAMILIES:
        raise ValueError("moderate catalog must contain the eight canonical families in order")
    densities = {str(key): int(value) for key, value in config.get("densities", {}).items()}
    if densities != EXPECTED_DENSITIES:
        raise ValueError("moderate densities must be low/medium/high = 1/2/4")
    moderation = config.get("moderation")
    if not isinstance(moderation, dict) or moderation.get("all_routes_one_shot") is not True:
        raise ValueError("moderate catalog must explicitly require one-shot routes")
    corridor_width = float(moderation["corridor_footprint_clear_width_m"])
    doorway_width = float(moderation["doorway_footprint_clear_width_m"])
    if not 2.4 <= corridor_width <= 2.8:
        raise ValueError("footprint-clear corridor width must be in [2.4, 2.8] m")
    if not 2.1 <= doorway_width <= 2.5:
        raise ValueError("footprint-clear doorway width must be in [2.1, 2.5] m")
    lane_min, lane_max = (float(value) for value in moderation["lane_offset_range_m"])
    if not 0.65 <= lane_min <= lane_max <= 0.90:
        raise ValueError("lane offsets must remain in [0.65, 0.90] m")
    avoidance = float(moderation["robot_avoidance_distance_m"])
    if not math.isfinite(avoidance) or avoidance <= COMBINED_COLLISION_RADIUS_M:
        raise ValueError("robot avoidance distance must exceed the 0.71 m combined collision radii")
    dynamics_keys = {
        "actor_dynamics_version",
        "robot_soft_yield_distance_m",
        "robot_hard_guard_distance_m",
        "actor_update_frequency_hz",
        "doorway_single_side_lane_stream",
        "doorway_lane_offset_m",
    }
    present_dynamics_keys = dynamics_keys & set(moderation)
    if present_dynamics_keys and present_dynamics_keys != dynamics_keys:
        missing = sorted(dynamics_keys - present_dynamics_keys)
        raise ValueError(f"actor dynamics configuration is incomplete: {missing}")
    if present_dynamics_keys:
        version = str(moderation["actor_dynamics_version"])
        if version != "deterministic_one_shot_swept_guard_v1":
            raise ValueError("unsupported actor_dynamics_version")
        soft_yield = float(moderation["robot_soft_yield_distance_m"])
        hard_guard = float(moderation["robot_hard_guard_distance_m"])
        update_frequency = float(moderation["actor_update_frequency_hz"])
        if not math.isclose(soft_yield, avoidance, abs_tol=1.0e-9):
            raise ValueError("soft yield distance must equal robot avoidance distance")
        if not COMBINED_COLLISION_RADIUS_M < hard_guard <= soft_yield:
            raise ValueError("hard guard must exceed collision radii and not exceed soft yield")
        if not math.isfinite(update_frequency) or update_frequency <= 0.0:
            raise ValueError("actor update frequency must be finite and positive")
        if moderation["doorway_single_side_lane_stream"] is not True:
            raise ValueError("v3 actor dynamics require the single-side doorway stream")
        doorway_lane_offset = float(moderation["doorway_lane_offset_m"])
        if not lane_min <= doorway_lane_offset <= lane_max:
            raise ValueError("doorway lane offset must lie inside the configured lane range")
    head_on_keys = {"head_on_single_side_lane_stream", "head_on_lane_offset_m"}
    present_head_on_keys = head_on_keys & set(moderation)
    if present_head_on_keys and present_head_on_keys != head_on_keys:
        missing = sorted(head_on_keys - present_head_on_keys)
        raise ValueError(f"head-on lane-stream configuration is incomplete: {missing}")
    if present_head_on_keys:
        if moderation["head_on_single_side_lane_stream"] is not True:
            raise ValueError("configured head-on lane stream must be single-sided")
        head_on_lane_offset = float(moderation["head_on_lane_offset_m"])
        if not lane_min <= head_on_lane_offset <= lane_max:
            raise ValueError("head-on lane offset must lie inside the configured lane range")
    present_v5_keys = V5_CALIBRATION_KEYS & set(moderation)
    if present_v5_keys and present_v5_keys != V5_CALIBRATION_KEYS:
        missing = sorted(V5_CALIBRATION_KEYS - present_v5_keys)
        raise ValueError(f"v5 calibration configuration is incomplete: {missing}")
    if present_v5_keys:
        if not present_dynamics_keys:
            raise ValueError("v5 calibration requires deterministic actor dynamics")
        vertical_end = float(moderation["blind_corner_vertical_end_y_m"])
        horizontal_start = float(moderation["blind_corner_horizontal_start_x_m"])
        if not 9.5 <= vertical_end <= 11.5:
            raise ValueError("blind-corner vertical endpoint must be in [9.5, 11.5] m")
        if not 14.5 <= horizontal_start <= 16.5:
            raise ValueError("blind-corner horizontal start must be in [14.5, 16.5] m")
        # These are the closest corners after the 0.40 m robot-footprint
        # inflation used by this catalog. Requiring positive clearance makes
        # the chamfer a real center-space route rather than a raster artifact.
        vertical_right = 13.5 + 0.20 + 0.40
        vertical_top = vertical_end + 0.45 + 0.40
        horizontal_left = horizontal_start - 0.45 - 0.40
        horizontal_bottom = 12.8 - 0.20 - 0.40
        chamfer_clearance = math.hypot(
            max(0.0, horizontal_left - vertical_right),
            max(0.0, horizontal_bottom - vertical_top),
        )
        if chamfer_clearance < 0.70:
            raise ValueError("blind-corner footprint-clear chamfer must be at least 0.70 m")
        group_offset = float(moderation["group_nearest_actor_offset_m"])
        if not hard_guard + 0.20 <= group_offset <= 1.30:
            raise ValueError("group nearest actor must leave at least 0.20 m beyond hard guard")
        for key in ("overtaking_lane_offset_range_m", "opposite_stream_lane_offset_range_m"):
            family_min, family_max = (float(value) for value in moderation[key])
            if not hard_guard + 0.08 <= family_min <= family_max <= 1.20:
                raise ValueError(f"{key} must remain in [hard_guard + 0.08, 1.20] m")
        temporary_half_gap = float(moderation["temporary_doorway_center_half_gap_m"])
        temporary_half_span = float(moderation["temporary_crossing_half_span_m"])
        temporary_spacing = float(moderation["temporary_crossing_x_spacing_m"])
        temporary_lead_in = float(moderation["temporary_crossing_lead_in_m"])
        if not 2.10 <= temporary_half_gap <= 2.35:
            raise ValueError("temporary doorway center half-gap must be in [2.10, 2.35] m")
        # Static shelf inner faces are half-gap - 0.45 m from the center.
        # Keep the pedestrian endpoints a radius-plus-margin inside them.
        if not 0.75 <= temporary_half_span <= temporary_half_gap - 0.80:
            raise ValueError("temporary crossing half-span lacks static endpoint clearance")
        if not 0.72 <= temporary_spacing <= 1.00:
            raise ValueError("temporary crossing x spacing must exceed two human radii")
        if not 0.8 <= temporary_lead_in <= 1.8:
            raise ValueError("temporary crossing lead-in must be in [0.8, 1.8] m")
        if moderation["validate_actor_static_clearance"] is not True:
            raise ValueError("v5 must validate complete actor routes against static geometry")
    families_by_id = {str(family["id"]): family for family in families}
    for family_id, key in EGRESS_EXIT_KEYS.items():
        if key not in moderation:
            continue
        exit_x = float(moderation[key])
        if not math.isfinite(exit_x):
            raise ValueError(f"{key} must be finite")
        robot_start_x = float(families_by_id[family_id]["robot_start"][0])
        if exit_x >= robot_start_x:
            raise ValueError(f"{key} must lie behind the {family_id} robot start")
    splits = config.get("splits")
    if not isinstance(splits, dict) or set(splits) not in (
        {"validation", "test"},
        {"train", "validation", "test"},
    ):
        raise ValueError("moderate benchmark must contain validation/test and optional train")
    for split, split_config in splits.items():
        _positive_repetitions(int(split_config["repetitions"]), split)
        if int(split_config["seed_base"]) < 0:
            raise ValueError(f"{split} seed base must be non-negative")
        offsets = split_config.get("geometry_offsets_m")
        if not isinstance(offsets, list) or not offsets:
            raise ValueError(f"{split} requires at least one geometry offset")
    _assert_seed_blocks_disjoint(
        {split: int(split_config["seed_base"]) for split, split_config in splits.items()}
    )


def _scenario_seed(seed_base: int, family_index: int, density_index: int, repeat: int) -> int:
    """Allocate non-overlapping decimal sub-blocks within one split seed block."""

    return seed_base + family_index * 100 + density_index * 10 + repeat


def _seeded_doorway_lane_side(seed: int) -> int:
    """Return a stable seed-selected side without relying on process hash state."""

    digest = hashlib.sha256(str(seed).encode()).digest()
    return -1 if digest[0] & 1 else 1


def _moderate_static_layout(
    base_compiler: ModuleType,
    layout: str,
    offset: float,
    *,
    blind_corner_vertical_end_y_m: float | None = None,
    blind_corner_horizontal_start_x_m: float | None = None,
    temporary_doorway_center_half_gap_m: float | None = None,
) -> list[dict[str, Any]]:
    """Build widened moderate geometry with known footprint-clear widths."""

    if layout in {"horizontal_corridor", "opposite_streams"}:
        # Shelf inner faces are y=10.30 and y=13.70. After 0.40 m
        # footprint inflation the center-space corridor remains 2.60 m wide.
        south = cast(
            list[dict[str, Any]],
            base_compiler._shelves_line((4.0, 10.10), (27.0, 10.10), prefix="south_moderate"),
        )
        north = cast(
            list[dict[str, Any]],
            base_compiler._shelves_line((4.0, 13.90), (27.0, 13.90), prefix="north_moderate"),
        )
        return south + north
    if layout in {"doorway", "temporary_blockage"}:
        center = 12.0 + offset
        center_half_gap = (
            2.0
            if layout != "temporary_blockage" or temporary_doorway_center_half_gap_m is None
            else temporary_doorway_center_half_gap_m
        )
        # The last/first shelf centers are exactly 4.0 m apart. Accounting for
        # 0.45 m shelf half-length and 0.40 m robot inflation on each side
        # leaves a 2.30 m center-space doorway.
        south = cast(
            list[dict[str, Any]],
            base_compiler._shelves_line(
                (15.5, 3.0),
                (15.5, center - center_half_gap),
                prefix="doorwall_south_moderate",
            ),
        )
        north = cast(
            list[dict[str, Any]],
            base_compiler._shelves_line(
                (15.5, center + center_half_gap),
                (15.5, 21.0),
                prefix="doorwall_north_moderate",
            ),
        )
        return south + north
    if layout == "blind_corner":
        # A finite L creates occlusion without the near-map-boundary detour in
        # the stress catalog. Both the robot and actors have collision-free
        # routes around the exposed right-hand tip.
        vertical_end_y = (
            12.8 if blind_corner_vertical_end_y_m is None else blind_corner_vertical_end_y_m
        )
        horizontal_start_x = (
            13.5 if blind_corner_horizontal_start_x_m is None else blind_corner_horizontal_start_x_m
        )
        vertical = cast(
            list[dict[str, Any]],
            base_compiler._shelves_line(
                (13.5, 6.0),
                (13.5, vertical_end_y),
                prefix="corner_v_moderate",
            ),
        )
        horizontal = cast(
            list[dict[str, Any]],
            base_compiler._shelves_line(
                (horizontal_start_x, 12.8),
                (20.5, 12.8),
                prefix="corner_h_moderate",
            ),
        )
        return vertical + horizontal
    return []


def _moderate_routes(
    layout: str,
    count: int,
    offset: float,
    *,
    lane_min: float,
    lane_max: float,
    longitudinal_stagger: float,
    head_on_exit_x_m: float | None = None,
    head_on_lane_side: int | None = None,
    head_on_lane_offset_m: float | None = None,
    doorway_exit_x_m: float | None = None,
    doorway_lane_side: int | None = None,
    doorway_lane_offset_m: float | None = None,
    group_nearest_actor_offset_m: float | None = None,
    overtaking_lane_offset_range_m: tuple[float, float] | None = None,
    opposite_stream_lane_offset_range_m: tuple[float, float] | None = None,
    temporary_crossing_half_span_m: float | None = None,
    temporary_crossing_x_spacing_m: float | None = None,
    temporary_crossing_lead_in_m: float | None = None,
) -> list[list[list[float]]]:
    """Return separated, longitudinally staggered one-shot actor routes."""

    if (head_on_lane_side is None) != (head_on_lane_offset_m is None):
        raise ValueError("head-on lane side and offset must be configured together")
    if head_on_lane_side is not None and head_on_lane_side not in {-1, 1}:
        raise ValueError("head-on lane side must be -1 or 1")
    if (doorway_lane_side is None) != (doorway_lane_offset_m is None):
        raise ValueError("doorway lane side and offset must be configured together")
    if doorway_lane_side is not None and doorway_lane_side not in {-1, 1}:
        raise ValueError("doorway lane side must be -1 or 1")
    lanes = (-lane_min, lane_min, -lane_max, lane_max)
    overtaking_lanes = lanes
    if overtaking_lane_offset_range_m is not None:
        overtaking_min, overtaking_max = overtaking_lane_offset_range_m
        overtaking_lanes = (-overtaking_min, overtaking_min, -overtaking_max, overtaking_max)
    opposite_stream_lanes = lanes
    if opposite_stream_lane_offset_range_m is not None:
        opposite_min, opposite_max = opposite_stream_lane_offset_range_m
        opposite_stream_lanes = (-opposite_min, opposite_min, -opposite_max, opposite_max)
    routes: list[list[list[float]]] = []
    for index in range(count):
        lane = lanes[index % len(lanes)] + offset
        stagger = longitudinal_stagger * index
        if layout == "horizontal_corridor":
            exit_x = 5.8 + 0.25 * index if head_on_exit_x_m is None else head_on_exit_x_m
            lane_y = (
                12.0 + lane
                if head_on_lane_side is None
                else 12.0 + offset + head_on_lane_side * float(head_on_lane_offset_m)
            )
            routes.append(
                [
                    [25.2 - stagger, lane_y, math.pi],
                    [exit_x, lane_y, math.pi],
                ]
            )
        elif layout == "doorway":
            exit_x = 12.0 - 0.35 * index if doorway_exit_x_m is None else doorway_exit_x_m
            if doorway_lane_side is None:
                routes.append(
                    [
                        [19.0 + stagger, 12.0 + lane, math.pi],
                        [exit_x, 12.0 - 0.45 * lane, math.pi],
                    ]
                )
            else:
                assert doorway_lane_offset_m is not None
                lane_y = 12.0 + offset + doorway_lane_side * doorway_lane_offset_m
                routes.append(
                    [
                        [19.0 + stagger, lane_y, math.pi],
                        [exit_x, lane_y, math.pi],
                    ]
                )
        elif layout == "crossing":
            x = 11.8 + 2.2 * index + offset
            if index % 2:
                routes.append([[x, 5.8 + 0.35 * index, math.pi / 2], [x, 18.2, math.pi / 2]])
            else:
                routes.append([[x, 18.2 - 0.35 * index, -math.pi / 2], [x, 5.8, -math.pi / 2]])
        elif layout == "blind_corner":
            start = [23.5 - 0.55 * index, 15.0 + 0.18 * lane, math.pi]
            around_tip_upper = [21.45 + 0.10 * index, 13.75 + 0.08 * lane, -math.pi / 2]
            around_tip_lower = [21.45 + 0.10 * index, 11.65 - 0.08 * lane, math.pi]
            goal = [14.4 + 0.55 * index, 11.65 - 0.18 * lane, math.pi]
            routes.append([start, around_tip_upper, around_tip_lower, goal])
        elif layout == "group_blocking":
            # Keep the group on the upper half of the corridor, leaving a
            # reproducible lower channel instead of sealing the full path.
            x = 14.8 + 1.15 * (index % 2) + 0.15 * offset
            y = (
                12.85 + 0.45 * (index // 2)
                if group_nearest_actor_offset_m is None
                else 12.0 + offset + group_nearest_actor_offset_m + 0.45 * (index // 2)
            )
            routes.append([[x, y, 0.0], [x + 0.35, y + (0.12 if index % 2 else -0.12), 0.0]])
        elif layout == "overtaking":
            x = 9.0 + stagger
            overtaking_lane = overtaking_lanes[index % len(overtaking_lanes)] + offset
            routes.append([[x, 12.0 + overtaking_lane, 0.0], [27.0, 12.0 + overtaking_lane, 0.0]])
        elif layout == "opposite_streams":
            opposite_lane = opposite_stream_lanes[index % len(opposite_stream_lanes)] + offset
            if index % 2:
                routes.append(
                    [
                        [5.8 + stagger, 12.0 + opposite_lane, 0.0],
                        [25.5, 12.0 + opposite_lane, 0.0],
                    ]
                )
            else:
                routes.append(
                    [
                        [25.5 - stagger, 12.0 + opposite_lane, math.pi],
                        [5.8, 12.0 + opposite_lane, math.pi],
                    ]
                )
        elif layout == "temporary_blockage":
            if (
                temporary_crossing_half_span_m is None
                or temporary_crossing_x_spacing_m is None
                or temporary_crossing_lead_in_m is None
            ):
                x = 15.5 + 0.18 * lane
                if index % 2:
                    routes.append([[x, 7.8 - 0.55 * index, math.pi / 2], [x, 16.2, math.pi / 2]])
                else:
                    routes.append([[x, 16.2 + 0.55 * index, -math.pi / 2], [x, 7.8, -math.pi / 2]])
            else:
                center_y = 12.0 + offset
                cross_x = 15.5 + (index - (count - 1) / 2.0) * temporary_crossing_x_spacing_m
                if index % 2:
                    lower_y = center_y - temporary_crossing_half_span_m
                    routes.append(
                        [
                            [cross_x + temporary_crossing_lead_in_m, lower_y, math.pi],
                            [cross_x, lower_y, math.pi],
                            [cross_x, center_y + temporary_crossing_half_span_m, math.pi / 2],
                        ]
                    )
                else:
                    upper_y = center_y + temporary_crossing_half_span_m
                    routes.append(
                        [
                            [cross_x - temporary_crossing_lead_in_m, upper_y, 0.0],
                            [cross_x, upper_y, 0.0],
                            [cross_x, center_y - temporary_crossing_half_span_m, -math.pi / 2],
                        ]
                    )
        else:
            raise ValueError(f"unknown scenario layout: {layout}")
    return routes


def _apply_moderation(
    scenario: dict[str, Any],
    family: dict[str, Any],
    base_compiler: ModuleType,
    config: dict[str, Any],
    *,
    offset: float,
    repeat: int,
) -> None:
    moderation = config["moderation"]
    layout = str(family["layout"])
    actors = scenario["obstacles"]["dynamic"]
    lane_min, lane_max = (float(value) for value in moderation["lane_offset_range_m"])
    single_side_doorway = bool(moderation.get("doorway_single_side_lane_stream", False))
    single_side_head_on = bool(moderation.get("head_on_single_side_lane_stream", False))
    head_on_lane_side = (
        _seeded_doorway_lane_side(int(scenario["ramp_metadata"]["seed"]))
        if layout == "horizontal_corridor" and single_side_head_on
        else None
    )
    head_on_lane_offset = (
        float(moderation["head_on_lane_offset_m"]) if head_on_lane_side is not None else None
    )
    doorway_lane_side = (
        _seeded_doorway_lane_side(int(scenario["ramp_metadata"]["seed"]))
        if layout == "doorway" and single_side_doorway
        else None
    )
    doorway_lane_offset = (
        float(moderation["doorway_lane_offset_m"]) if doorway_lane_side is not None else None
    )
    overtaking_lane_range = (
        tuple(float(value) for value in moderation["overtaking_lane_offset_range_m"])
        if "overtaking_lane_offset_range_m" in moderation
        else None
    )
    opposite_stream_lane_range = (
        tuple(float(value) for value in moderation["opposite_stream_lane_offset_range_m"])
        if "opposite_stream_lane_offset_range_m" in moderation
        else None
    )
    routes = _moderate_routes(
        layout,
        len(actors),
        offset,
        lane_min=lane_min,
        lane_max=lane_max,
        longitudinal_stagger=float(moderation["pedestrian_longitudinal_stagger_m"]),
        head_on_exit_x_m=(
            float(moderation["head_on_exit_x_m"]) if "head_on_exit_x_m" in moderation else None
        ),
        head_on_lane_side=head_on_lane_side,
        head_on_lane_offset_m=head_on_lane_offset,
        doorway_exit_x_m=(
            float(moderation["doorway_exit_x_m"]) if "doorway_exit_x_m" in moderation else None
        ),
        doorway_lane_side=doorway_lane_side,
        doorway_lane_offset_m=doorway_lane_offset,
        group_nearest_actor_offset_m=(
            float(moderation["group_nearest_actor_offset_m"])
            if "group_nearest_actor_offset_m" in moderation
            else None
        ),
        overtaking_lane_offset_range_m=cast(
            tuple[float, float] | None,
            overtaking_lane_range,
        ),
        opposite_stream_lane_offset_range_m=cast(
            tuple[float, float] | None,
            opposite_stream_lane_range,
        ),
        temporary_crossing_half_span_m=(
            float(moderation["temporary_crossing_half_span_m"])
            if "temporary_crossing_half_span_m" in moderation
            else None
        ),
        temporary_crossing_x_spacing_m=(
            float(moderation["temporary_crossing_x_spacing_m"])
            if "temporary_crossing_x_spacing_m" in moderation
            else None
        ),
        temporary_crossing_lead_in_m=(
            float(moderation["temporary_crossing_lead_in_m"])
            if "temporary_crossing_lead_in_m" in moderation
            else None
        ),
    )
    scenario["obstacles"]["static"] = _moderate_static_layout(
        base_compiler,
        layout,
        offset,
        blind_corner_vertical_end_y_m=(
            float(moderation["blind_corner_vertical_end_y_m"])
            if "blind_corner_vertical_end_y_m" in moderation
            else None
        ),
        blind_corner_horizontal_start_x_m=(
            float(moderation["blind_corner_horizontal_start_x_m"])
            if "blind_corner_horizontal_start_x_m" in moderation
            else None
        ),
        temporary_doorway_center_half_gap_m=(
            float(moderation["temporary_doorway_center_half_gap_m"])
            if "temporary_doorway_center_half_gap_m" in moderation
            else None
        ),
    )
    metadata = scenario["ramp_metadata"]
    metadata["benchmark_id"] = str(config["benchmark_id"])
    metadata["difficulty"] = "moderate"
    metadata["replicate"] = repeat
    dynamics_version = moderation.get("actor_dynamics_version")
    metadata["human_behavior_model"] = (
        str(dynamics_version)
        if dynamics_version is not None
        else "deterministic one-shot waypoint kinematic proxy"
    )
    metadata["moderation"] = {
        "corridor_footprint_clear_width_m": float(moderation["corridor_footprint_clear_width_m"]),
        "doorway_footprint_clear_width_m": float(moderation["doorway_footprint_clear_width_m"]),
        "lane_offset_range_m": [lane_min, lane_max],
        "pedestrian_longitudinal_stagger_m": float(moderation["pedestrian_longitudinal_stagger_m"]),
        "robot_avoidance_distance_m": float(moderation["robot_avoidance_distance_m"]),
        "group_clear_channel_width_m": float(moderation["group_clear_channel_width_m"]),
    }
    for key in sorted(V5_CALIBRATION_KEYS - {"validate_actor_static_clearance"}):
        if key in moderation:
            value = moderation[key]
            metadata["moderation"][key] = (
                [float(item) for item in value] if isinstance(value, list) else float(value)
            )
    if "validate_actor_static_clearance" in moderation:
        metadata["moderation"]["validate_actor_static_clearance"] = bool(
            moderation["validate_actor_static_clearance"]
        )
    for key in EGRESS_EXIT_KEYS.values():
        if key in moderation:
            metadata["moderation"][key] = float(moderation[key])
    if dynamics_version is not None:
        actor_behavior = {
            "robot_soft_yield_distance_m": float(moderation["robot_soft_yield_distance_m"]),
            "robot_hard_guard_distance_m": float(moderation["robot_hard_guard_distance_m"]),
            "actor_update_frequency_hz": float(moderation["actor_update_frequency_hz"]),
        }
        metadata["actor_dynamics_version"] = str(dynamics_version)
        metadata["actor_behavior_parameters"] = actor_behavior
        metadata["moderation"].update(actor_behavior)
        metadata["moderation"]["actor_dynamics_version"] = str(dynamics_version)
    if doorway_lane_side is not None:
        assert doorway_lane_offset is not None
        doorway_center_y = 12.0 + offset
        metadata["doorway_stream"] = {
            "lane_side": doorway_lane_side,
            "lane_offset_m": doorway_lane_offset,
            "lane_y_m": doorway_center_y + doorway_lane_side * doorway_lane_offset,
            "recovery_channel_y_m": doorway_center_y - doorway_lane_side * doorway_lane_offset,
            "lane_preserving": True,
        }
    if head_on_lane_side is not None:
        assert head_on_lane_offset is not None
        head_on_center_y = 12.0 + offset
        metadata["head_on_stream"] = {
            "lane_side": head_on_lane_side,
            "lane_offset_m": head_on_lane_offset,
            "lane_y_m": head_on_center_y + head_on_lane_side * head_on_lane_offset,
            "recovery_channel_y_m": head_on_center_y - head_on_lane_side * head_on_lane_offset,
            "lane_preserving": True,
            "seed_deterministic": True,
        }
    for actor, route in zip(actors, routes, strict=True):
        actor["pos"] = route[0]
        actor["waypoints"] = route
        actor["cyclic_goals"] = False
        actor["robot_avoidance_distance_m"] = float(moderation["robot_avoidance_distance_m"])
        actor["behavior"]["once"] = True
        if dynamics_version is not None:
            actor["actor_dynamics_version"] = str(dynamics_version)
            actor["robot_soft_yield_distance_m"] = float(moderation["robot_soft_yield_distance_m"])
            actor["robot_hard_guard_distance_m"] = float(moderation["robot_hard_guard_distance_m"])
            actor["actor_update_frequency_hz"] = float(moderation["actor_update_frequency_hz"])
            actor["behavior"].update(
                {
                    "actor_dynamics_version": str(dynamics_version),
                    "robot_soft_yield_distance_m": float(moderation["robot_soft_yield_distance_m"]),
                    "robot_hard_guard_distance_m": float(moderation["robot_hard_guard_distance_m"]),
                    "actor_update_frequency_hz": float(moderation["actor_update_frequency_hz"]),
                }
            )


def _validate_configured_egress_endpoints(
    scenario: dict[str, Any],
    bounds: list[float],
    resolution: float,
    moderation: dict[str, Any],
) -> None:
    """Validate optional one-shot egress endpoints without changing v1 routes."""

    family = str(scenario["ramp_metadata"]["family"])
    key = EGRESS_EXIT_KEYS.get(family)
    if key is None or key not in moderation:
        return
    robot_start_x = float(scenario["robots"][0]["start"][0])
    for actor in scenario["obstacles"]["dynamic"]:
        endpoint = actor["waypoints"][-1]
        endpoint_x = float(endpoint[0])
        endpoint_y = float(endpoint[1])
        if endpoint_x >= robot_start_x:
            raise ValueError(f"{family} egress endpoint must lie behind the robot start")
        human_radius = float(actor.get("radius", 0.35))
        grid = _footprint_occupancy(scenario, bounds, resolution, human_radius)
        if not grid.is_free(grid.world_to_grid(endpoint_x, endpoint_y)):
            raise ValueError(f"{family} egress endpoint intersects inflated static geometry")


def _validate_actor_routes_against_static_geometry(
    scenario: dict[str, Any],
    bounds: list[float],
    resolution: float,
    moderation: dict[str, Any],
) -> None:
    """Require every actor waypoint and segment to clear inflated shelves."""

    if not bool(moderation.get("validate_actor_static_clearance", False)):
        return
    family = str(scenario["ramp_metadata"]["family"])
    for actor in scenario["obstacles"]["dynamic"]:
        radius = float(actor.get("radius", 0.35))
        grid = _footprint_occupancy(scenario, bounds, resolution, radius)
        points = [(float(point[0]), float(point[1])) for point in actor["waypoints"]]
        if any(not grid.is_free(grid.world_to_grid(*point)) for point in points):
            raise ValueError(f"{family} actor waypoint intersects radius-inflated static geometry")
        if any(not grid.segment_is_free(left, right) for left, right in pairwise(points)):
            raise ValueError(f"{family} actor segment intersects radius-inflated static geometry")


def _validate_single_side_doorway_stream(
    scenario: dict[str, Any],
    bounds: list[float],
    resolution: float,
    footprint_inflation_m: float,
    moderation: dict[str, Any],
) -> None:
    """Validate the v3 lane stream and its static-map-free recovery channel."""

    if not bool(moderation.get("doorway_single_side_lane_stream", False)):
        return
    if str(scenario["ramp_metadata"]["family"]) != "doorway_bottleneck":
        return
    stream = scenario["ramp_metadata"].get("doorway_stream")
    if not isinstance(stream, dict) or stream.get("lane_preserving") is not True:
        raise ValueError("single-side doorway stream metadata is missing")
    lane_y = float(stream["lane_y_m"])
    actors = scenario["obstacles"]["dynamic"]
    for actor in actors:
        waypoint_y = [float(point[1]) for point in actor["waypoints"]]
        if any(not math.isclose(value, lane_y, abs_tol=1.0e-9) for value in waypoint_y):
            raise ValueError("doorway actor route crosses lanes")
    robot = scenario["robots"][0]
    recovery_y = float(stream["recovery_channel_y_m"])
    grid = _footprint_occupancy(scenario, bounds, resolution, footprint_inflation_m)
    channel_start = (float(robot["start"][0]), recovery_y)
    channel_goal = (float(robot["goal"][0]), recovery_y)
    if not grid.segment_is_free(channel_start, channel_goal):
        raise ValueError("doorway opposite-side recovery channel intersects static geometry")


def _validate_single_side_head_on_stream(
    scenario: dict[str, Any],
    bounds: list[float],
    resolution: float,
    footprint_inflation_m: float,
    moderation: dict[str, Any],
) -> None:
    """Validate the seed-selected, lane-preserving v4 head-on stream."""

    if not bool(moderation.get("head_on_single_side_lane_stream", False)):
        return
    if str(scenario["ramp_metadata"]["family"]) != "head_on_corridor":
        return
    stream = scenario["ramp_metadata"].get("head_on_stream")
    if not isinstance(stream, dict) or stream.get("lane_preserving") is not True:
        raise ValueError("single-side head-on stream metadata is missing")
    if stream.get("seed_deterministic") is not True:
        raise ValueError("head-on stream side must be seed-deterministic")
    seed = int(scenario["ramp_metadata"]["seed"])
    if int(stream["lane_side"]) != _seeded_doorway_lane_side(seed):
        raise ValueError("head-on stream side does not match its seed")
    lane_y = float(stream["lane_y_m"])
    recovery_y = float(stream["recovery_channel_y_m"])
    if abs(lane_y - recovery_y) <= COMBINED_COLLISION_RADIUS_M:
        raise ValueError("head-on actor lane does not leave a collision-clear recovery channel")
    actors = scenario["obstacles"]["dynamic"]
    for actor in actors:
        waypoint_y = [float(point[1]) for point in actor["waypoints"]]
        if any(not math.isclose(value, lane_y, abs_tol=1.0e-9) for value in waypoint_y):
            raise ValueError("head-on actor routes must remain on one shared lane")
    starts = sorted(float(actor["waypoints"][0][0]) for actor in actors)
    expected_stagger = float(moderation["pedestrian_longitudinal_stagger_m"])
    if any(
        not math.isclose(right - left, expected_stagger, abs_tol=1.0e-9)
        for left, right in pairwise(starts)
    ):
        raise ValueError("head-on stream does not preserve longitudinal staggering")
    robot = scenario["robots"][0]
    grid = _footprint_occupancy(scenario, bounds, resolution, footprint_inflation_m)
    channel_start = (float(robot["start"][0]), recovery_y)
    channel_goal = (float(robot["goal"][0]), recovery_y)
    if not grid.segment_is_free(channel_start, channel_goal):
        raise ValueError("head-on opposite-side recovery channel intersects static geometry")


def _footprint_occupancy(
    scenario: dict[str, Any],
    bounds: list[float],
    resolution: float,
    footprint_inflation_m: float,
) -> OccupancyGrid:
    """Rasterize actual shelf boxes inflated by the circular robot footprint."""

    if resolution <= 0.0 or footprint_inflation_m <= 0.0:
        raise ValueError("resolution and footprint inflation must be positive")
    x_min, x_max, y_min, y_max = bounds
    width = math.ceil((x_max - x_min) / resolution)
    height = math.ceil((y_max - y_min) / resolution)
    occupied = np.zeros((height, width), dtype=np.bool_)
    border = math.ceil(footprint_inflation_m / resolution)
    occupied[:border, :] = True
    occupied[-border:, :] = True
    occupied[:, :border] = True
    occupied[:, -border:] = True
    for item in scenario["obstacles"]["static"]:
        if item.get("model") != "shelf":
            raise ValueError(f"unsupported static model: {item.get('model')!r}")
        x, y, yaw = (float(value) for value in item["pos"])
        horizontal = abs(math.cos(yaw)) >= abs(math.sin(yaw))
        half_x = (0.45 if horizontal else 0.20) + footprint_inflation_m
        half_y = (0.20 if horizontal else 0.45) + footprint_inflation_m
        column_start = max(0, math.floor((x - half_x - x_min) / resolution))
        column_end = min(width, math.ceil((x + half_x - x_min) / resolution))
        row_start = max(0, math.floor((y - half_y - y_min) / resolution))
        row_end = min(height, math.ceil((y + half_y - y_min) / resolution))
        occupied[row_start:row_end, column_start:column_end] = True
    return OccupancyGrid(occupied, resolution, x_min, y_min)


def _footprint_path(
    scenario: dict[str, Any],
    bounds: list[float],
    resolution: float,
    footprint_inflation_m: float,
) -> tuple[OccupancyGrid, tuple[tuple[int, int], ...]]:
    grid = _footprint_occupancy(scenario, bounds, resolution, footprint_inflation_m)
    robot = scenario["robots"][0]
    start = grid.world_to_grid(float(robot["start"][0]), float(robot["start"][1]))
    goal = grid.world_to_grid(float(robot["goal"][0]), float(robot["goal"][1]))
    cells = tuple(astar(grid, start, goal))
    if not cells:
        scenario_id = scenario["ramp_metadata"]["scenario_id"]
        raise ValueError(f"footprint-inflated A* found no path for {scenario_id}")
    return grid, cells


def _render_preview(
    scenario: dict[str, Any],
    grid: OccupancyGrid,
    cells: tuple[tuple[int, int], ...],
    bounds: list[float],
    destination: Path,
) -> None:
    world_path = np.asarray([grid.grid_to_world(cell) for cell in cells])
    figure, axis = plt.subplots(figsize=(7.2, 5.5), constrained_layout=True)
    axis.set_xlim(bounds[0], bounds[1])
    axis.set_ylim(bounds[2], bounds[3])
    axis.set_aspect("equal")
    for item in scenario["obstacles"]["static"]:
        x, y, yaw = (float(value) for value in item["pos"])
        horizontal = abs(math.cos(yaw)) >= abs(math.sin(yaw))
        width, height = (0.9, 0.4) if horizontal else (0.4, 0.9)
        axis.add_patch(Rectangle((x - width / 2, y - height / 2), width, height, color="0.28"))
    axis.plot(
        world_path[:, 0],
        world_path[:, 1],
        color="#0072B2",
        linewidth=2.0,
        label="footprint-inflated A*",
    )
    robot = scenario["robots"][0]
    start = robot["start"]
    goal = robot["goal"]
    axis.scatter(start[0], start[1], color="#009E73", s=55, label="robot start", zorder=4)
    axis.scatter(goal[0], goal[1], color="#D55E00", marker="*", s=105, label="robot goal", zorder=4)
    for index, actor in enumerate(scenario["obstacles"]["dynamic"]):
        first, last = actor["waypoints"][0], actor["waypoints"][-1]
        axis.scatter(first[0], first[1], color="#E69F00", s=27, zorder=4)
        axis.annotate(
            "",
            xy=(last[0], last[1]),
            xytext=(first[0], first[1]),
            arrowprops={"arrowstyle": "->", "color": "#E69F00", "alpha": 0.75},
        )
        axis.text(first[0] + 0.10, first[1] + 0.10, str(index), fontsize=7)
    metadata = scenario["ramp_metadata"]
    axis.set_title(
        f"{metadata['family']} / {metadata['density']} / "
        f"{metadata['split']} r{metadata['replicate']}"
    )
    axis.set_xlabel("x [m]")
    axis.set_ylabel("y [m]")
    axis.legend(loc="upper right", fontsize=7)
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(destination, dpi=150)
    plt.close(figure)


def _assert_split_isolation(compiled: list[CompiledScenario]) -> None:
    values: dict[str, dict[str, set[Any]]] = {}
    split_order = tuple(dict.fromkeys(item.split for item in compiled))
    if not split_order:
        raise ValueError("compiled benchmark must contain at least one split")
    for split in split_order:
        rows = [item.record for item in compiled if item.split == split]
        values[split] = {
            "scenario IDs": {row["scenario_id"] for row in rows},
            "seeds": {row["seed"] for row in rows},
            "scenario hashes": {row["sha256"] for row in rows},
        }
        if len(values[split]["scenario IDs"]) != len(rows):
            raise ValueError(f"duplicate scenario ID inside {split}")
        if len(values[split]["seeds"]) != len(rows):
            raise ValueError(f"duplicate seed inside {split}")
        if len(values[split]["scenario hashes"]) != len(rows):
            raise ValueError(f"duplicate scenario hash inside {split}")
    for left, right in combinations(split_order, 2):
        for label in values[left]:
            overlap = values[left][label] & values[right][label]
            if overlap:
                raise ValueError(f"{left}/{right} {label} leakage: {sorted(overlap)!r}")


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def compile_benchmark(
    config_path: Path,
    output_root: Path,
    *,
    train_repetitions: int | None = None,
    validation_repetitions: int | None = None,
    test_repetitions: int | None = None,
    train_seed_base: int | None = None,
    validation_seed_base: int | None = None,
    test_seed_base: int | None = None,
    manifest_suffix: str | None = None,
    render_previews: bool = True,
) -> dict[str, Any]:
    """Compile deterministic moderate scenarios and split manifests."""

    config_path = config_path.resolve()
    output_root = output_root.resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    _validate_config(config)
    suffix = _validate_suffix(manifest_suffix or str(config["output"]["manifest_suffix"]))
    default_suffix = _validate_suffix(str(config["output"]["manifest_suffix"]))
    generated_subdirectory = Path(str(config["output"]["generated_subdirectory"]))
    preview_subdirectory = Path(str(config["output"]["preview_subdirectory"]))
    if suffix != default_suffix:
        generated_subdirectory = Path(suffix) / "arena"
        preview_subdirectory = Path(suffix)

    split_overrides = {
        "train": {
            "repetitions": train_repetitions,
            "seed_base": train_seed_base,
        },
        "validation": {
            "repetitions": validation_repetitions,
            "seed_base": validation_seed_base,
        },
        "test": {"repetitions": test_repetitions, "seed_base": test_seed_base},
    }
    split_order = tuple(str(split) for split in config["splits"])
    for split, overrides in split_overrides.items():
        if split not in split_order and any(value is not None for value in overrides.values()):
            raise ValueError(f"{split} overrides require a configured {split} split")
    resolved_repetitions: dict[str, int] = {}
    resolved_seed_bases: dict[str, int] = {}
    for split in split_order:
        overrides = split_overrides[split]
        split_config = config["splits"][split]
        repetitions = overrides["repetitions"]
        seed_base = overrides["seed_base"]
        resolved_repetitions[split] = _positive_repetitions(
            int(split_config["repetitions"] if repetitions is None else repetitions), split
        )
        resolved_seed_bases[split] = int(
            split_config["seed_base"] if seed_base is None else seed_base
        )
        if resolved_seed_bases[split] < 0:
            raise ValueError(f"{split} seed base must be non-negative")
    _assert_seed_blocks_disjoint(resolved_seed_bases)

    bounds = [float(value) for value in config["map"]["bounds_m"]]
    resolution = float(config["map"]["preview_resolution_m"])
    map_id = str(config["map"]["id"])
    footprint_inflation = float(config["robot"]["radius_m"]) + float(
        config["robot"]["static_path_margin_m"]
    )
    base_compiler = _load_base_compiler()
    compiled: list[CompiledScenario] = []

    for split in split_order:
        split_config = config["splits"][split]
        repetitions = resolved_repetitions[split]
        seed_base = resolved_seed_bases[split]
        offsets = [float(value) for value in split_config["geometry_offsets_m"]]
        for family_index, family in enumerate(config["families"]):
            for density_index, (density, count) in enumerate(config["densities"].items()):
                for repeat in range(repetitions):
                    seed = _scenario_seed(seed_base, family_index, density_index, repeat)
                    geometry_offset = offsets[repeat % len(offsets)]
                    scenario = base_compiler._build_scenario(
                        family,
                        density=str(density),
                        count=int(count),
                        split=split,
                        seed=seed,
                        offset=geometry_offset,
                        map_id=map_id,
                    )
                    scenario_id = (
                        f"{family['id']}_{density}_{split}_{suffix}_r{repeat:02d}_s{seed:05d}"
                    )
                    scenario["ramp_metadata"]["scenario_id"] = scenario_id
                    _apply_moderation(
                        scenario,
                        family,
                        base_compiler,
                        config,
                        offset=geometry_offset,
                        repeat=repeat,
                    )
                    base_compiler._validate_scenario(scenario, bounds)
                    _validate_configured_egress_endpoints(
                        scenario,
                        bounds,
                        resolution,
                        config["moderation"],
                    )
                    _validate_actor_routes_against_static_geometry(
                        scenario,
                        bounds,
                        resolution,
                        config["moderation"],
                    )
                    _validate_single_side_doorway_stream(
                        scenario,
                        bounds,
                        resolution,
                        footprint_inflation,
                        config["moderation"],
                    )
                    _validate_single_side_head_on_stream(
                        scenario,
                        bounds,
                        resolution,
                        footprint_inflation,
                        config["moderation"],
                    )
                    _, path_cells = _footprint_path(
                        scenario,
                        bounds,
                        resolution,
                        footprint_inflation,
                    )
                    relative = generated_subdirectory / map_id / f"{scenario_id}.json"
                    preview_relative = preview_subdirectory / f"{scenario_id}.png"
                    serialized = json.dumps(scenario, indent=2, sort_keys=True) + "\n"
                    digest = hashlib.sha256(serialized.encode()).hexdigest()
                    record = {
                        "scenario_id": scenario_id,
                        "family": str(family["id"]),
                        "density": str(density),
                        "map_id": map_id,
                        "seed": seed,
                        "replicate": repeat,
                        "difficulty": "moderate",
                        "path": str(relative),
                        "preview": str(Path("previews") / preview_relative),
                        "sha256": digest,
                    }
                    compiled.append(
                        CompiledScenario(
                            split=split,
                            record=record,
                            payload=scenario,
                            serialized=serialized,
                            relative_path=relative,
                            preview_relative_path=preview_relative,
                            path_cells=path_cells,
                        )
                    )

    _assert_split_isolation(compiled)
    manifests: dict[str, list[dict[str, Any]]] = {split: [] for split in split_order}
    for item in compiled:
        destination = output_root / "generated" / item.relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(item.serialized, encoding="utf-8")
        if render_previews:
            grid, cells = _footprint_path(
                item.payload,
                bounds,
                resolution,
                footprint_inflation,
            )
            if cells != item.path_cells:
                raise RuntimeError("A* path changed between validation and rendering")
            _render_preview(
                item.payload,
                grid,
                cells,
                bounds,
                output_root / "previews" / item.preview_relative_path,
            )
        manifests[item.split].append(item.record)

    manifest_directory = output_root / "splits"
    manifest_directory.mkdir(parents=True, exist_ok=True)
    manifest_paths: dict[str, str] = {}
    for split, records in manifests.items():
        manifest_path = manifest_directory / f"{suffix}_{split}.yaml"
        manifest_path.write_text(
            yaml.safe_dump(
                {
                    "schema_version": 1,
                    "benchmark_id": str(config["benchmark_id"]),
                    "difficulty": "moderate",
                    "manifest_suffix": suffix,
                    "split": split,
                    "scenarios": records,
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        manifest_paths[split] = _relative_or_absolute(manifest_path, output_root)

    scenario_ids = sorted(item.record["scenario_id"] for item in compiled)
    summary = {
        "schema_version": 1,
        "benchmark_id": str(config["benchmark_id"]),
        "difficulty": "moderate",
        "source_config": _relative_or_absolute(config_path, ROOT),
        "manifest_suffix": suffix,
        "manifest_paths": manifest_paths,
        "counts_by_split": {split: len(records) for split, records in manifests.items()},
        "scenario_count": len(compiled),
        **{f"{split}_seed_base": resolved_seed_bases[split] for split in split_order},
        "footprint_inflation_m": footprint_inflation,
        "scenario_ids_sha256": hashlib.sha256("\n".join(scenario_ids).encode()).hexdigest(),
    }
    summary_directory = output_root / "manifests"
    summary_directory.mkdir(parents=True, exist_ok=True)
    (summary_directory / f"scenario_catalog_{suffix}.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=ROOT / "scenarios")
    parser.add_argument("--train-repetitions", type=int)
    parser.add_argument("--validation-repetitions", type=int)
    parser.add_argument("--test-repetitions", type=int)
    parser.add_argument("--train-seed-base", type=int)
    parser.add_argument("--validation-seed-base", type=int)
    parser.add_argument("--test-seed-base", type=int)
    parser.add_argument("--manifest-suffix")
    parser.add_argument("--no-previews", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = compile_benchmark(
        args.config,
        args.output_root,
        train_repetitions=args.train_repetitions,
        validation_repetitions=args.validation_repetitions,
        test_repetitions=args.test_repetitions,
        train_seed_base=args.train_seed_base,
        validation_seed_base=args.validation_seed_base,
        test_seed_base=args.test_seed_base,
        manifest_suffix=args.manifest_suffix,
        render_previews=not args.no_previews,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
