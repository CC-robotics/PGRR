#!/usr/bin/env python3
"""Replay the three upstream action-mask layers on deterministic synthetic inputs."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from ramp_core.action_mask import (
    ActionMaskConfig,
    apply_observable_scan_mask,
    apply_path_corridor_mask,
    compute_action_mask,
)
from ramp_core.occupancy import OccupancyGrid
from ramp_core.recovery.mask_trace import MaskTraceRecorder
from ramp_core.types import Pose2D

SUBGOAL_IDS = tuple(range(21))


def _grid(*, locally_enclosed: bool) -> OccupancyGrid:
    occupied = np.zeros((120, 120), dtype=np.bool_)
    if locally_enclosed:
        occupied[:] = True
        center = 60
        for row in range(center - 3, center + 4):
            for column in range(center - 3, center + 4):
                if (row - center) ** 2 + (column - center) ** 2 <= 9:
                    occupied[row, column] = False
    return OccupancyGrid(occupied, resolution=0.1)


def _retained(mask: np.ndarray[Any, np.dtype[np.bool_]]) -> list[int]:
    return [action_id for action_id in SUBGOAL_IDS if bool(mask[action_id])]


def run_fixture(
    name: str,
    *,
    locally_enclosed: bool = False,
    lidar_range_m: float = 8.0,
    corridor_width_m: float = 2.0,
    trace_enabled: bool = True,
) -> dict[str, Any]:
    pose = Pose2D(6.05, 6.05, 0.0)
    recorder = MaskTraceRecorder(enabled=trace_enabled)
    initial_mask = np.ones(25, dtype=np.bool_)
    computed_map_mask = compute_action_mask(
        pose,
        _grid(locally_enclosed=locally_enclosed),
        replan_available=True,
        config=ActionMaskConfig(robot_clearance=0.25, backup_distance=0.45),
    )
    map_mask = recorder.record("map_connectivity", initial_mask, computed_map_mask)
    ranges = np.full(360, lidar_range_m, dtype=np.float64)
    computed_scan_mask = apply_observable_scan_mask(
        map_mask,
        ranges,
        angle_min=-math.pi,
        angle_increment=2.0 * math.pi / 360.0,
        swept_clearance_m=0.48,
        target_clearance_m=0.25,
        backup_distance_m=0.45,
    )
    scan_mask = recorder.record("observable_scan", map_mask, computed_scan_mask)
    computed_corridor_mask = apply_path_corridor_mask(
        scan_mask,
        pose,
        ((2.0, pose.y), (10.0, pose.y)),
        maximum_deviation_m=corridor_width_m,
        backup_distance_m=0.45,
    )
    corridor_mask = recorder.record("path_corridor", scan_mask, computed_corridor_mask)
    stages = []
    previous = set(SUBGOAL_IDS)
    for stage_name, mask in (
        ("map_connectivity", map_mask),
        ("observable_scan", scan_mask),
        ("path_corridor", corridor_mask),
    ):
        retained = _retained(mask)
        retained_set = set(retained)
        stages.append(
            {
                "stage": stage_name,
                "retained_subgoal_ids": retained,
                "retained_subgoal_count": len(retained),
                "removed_at_stage": sorted(previous - retained_set),
            }
        )
        previous = retained_set
    return {
        "fixture": name,
        "parameters": {
            "locally_enclosed": locally_enclosed,
            "lidar_range_m": lidar_range_m,
            "corridor_width_m": corridor_width_m,
        },
        "stages": stages,
        "selected_action_id": int(np.flatnonzero(corridor_mask)[0]),
        "trace": recorder.as_dict(),
    }


def build_report() -> dict[str, Any]:
    fixtures = [
        run_fixture("open_control"),
        run_fixture("map_enclosed", locally_enclosed=True),
        run_fixture("lidar_close_returns", lidar_range_m=0.30),
        run_fixture("narrow_path_corridor", corridor_width_m=0.20),
    ]
    return {
        "claim_boundary": "synthetic_layer_replay_not_episode_ablation",
        "seed": 0,
        "fixtures": fixtures,
        "equivalence_contract": "trace_observes_detached_masks_without_changing_selection",
    }


def write_outputs(report: dict[str, Any], json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rows = []
    for fixture in report["fixtures"]:
        for stage in fixture["stages"]:
            rows.append(
                {
                    "fixture": fixture["fixture"],
                    "stage": stage["stage"],
                    "retained_subgoal_count": stage["retained_subgoal_count"],
                    "retained_subgoal_ids": ",".join(map(str, stage["retained_subgoal_ids"])),
                    "removed_at_stage": ",".join(map(str, stage["removed_at_stage"])),
                }
            )
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report()
    write_outputs(report, args.json_output, args.csv_output)
    summary = {
        fixture["fixture"]: [stage["retained_subgoal_count"] for stage in fixture["stages"]]
        for fixture in report["fixtures"]
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
