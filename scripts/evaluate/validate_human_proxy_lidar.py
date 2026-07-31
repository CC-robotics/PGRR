#!/usr/bin/env python3
"""Reject episodes whose privileged human proxy is absent from LiDAR."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from ramp_core.evaluation.sensor_consistency import nearest_human_lidar_consistency


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("episode", type=Path)
    parser.add_argument("--near-distance", type=float, default=1.3)
    parser.add_argument("--tolerance", type=float, default=0.2)
    parser.add_argument("--minimum-samples", type=int, default=5)
    parser.add_argument("--minimum-visible-ratio", type=float, default=0.9)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    near: list[dict[str, Any]] = []
    with args.episode.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            check = nearest_human_lidar_consistency(
                row["robot_pose"],
                np.asarray(row["lidar"], dtype=np.float32),
                row.get("privileged", {}).get("human_positions", []),
            )
            if check is None or check.center_distance_m >= args.near_distance:
                continue
            near.append(
                {
                    "timestamp": row["timestamp"],
                    "center_distance_m": check.center_distance_m,
                    "expected_surface_distance_m": check.expected_surface_distance_m,
                    "sector_distance_m": check.sector_distance_m,
                    "visible": check.is_visible(args.tolerance),
                }
            )
    visible_count = sum(bool(item["visible"]) for item in near)
    ratio = visible_count / len(near) if near else 0.0
    passed = len(near) >= args.minimum_samples and ratio >= args.minimum_visible_ratio
    payload = {
        "episode": str(args.episode),
        "near_distance_m": args.near_distance,
        "tolerance_m": args.tolerance,
        "near_sample_count": len(near),
        "visible_sample_count": visible_count,
        "visible_ratio": ratio,
        "minimum_center_distance_m": min(
            (item["center_distance_m"] for item in near), default=None
        ),
        "maximum_surface_range_error_m": max(
            (item["sector_distance_m"] - item["expected_surface_distance_m"] for item in near),
            default=None,
        ),
        "passed": passed,
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
